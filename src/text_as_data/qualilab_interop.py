from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field

from .db import DocumentRecord, ExtractionRecord, HumanLabelRecord
from .extraction import ERROR_CATEGORY

# See docs/superpowers/specs/2026-09-02-qualilab-interop-design.md for the
# full design and the three rounds of adversarial review behind every
# decision in this module -- comments here cite finding numbers from that
# document rather than re-explaining the reasoning inline.

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB (finding #3)


def open_qualilab_project(content: bytes) -> dict:
    """Parse a `.qualilab` file's raw bytes into its `project.json` dict.

    Detects the container shape by its first two bytes (`PK` = zip, per
    QualiLab's own documented read algorithm) rather than trusting a file
    extension. Raises `ValueError` (not an HTTP-specific exception -- the
    caller in app.py maps this to a 400/413, matching how
    corpus_import.py's parse_csv_rows/parse_xlsx_rows already do it) on
    anything malformed or oversized, never a bare crash.
    """
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError(f"upload exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")

    if content[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                try:
                    info = archive.getinfo("project.json")
                except KeyError as exc:
                    raise ValueError("zip .qualilab file has no project.json entry") from exc
                # Checked via the zip's own directory metadata, before ever
                # decompressing -- a crafted high-ratio entry is rejected
                # without spending the memory a real read() would cost
                # (finding #3: a decompression-bomb-style upload). A
                # smaller-than-real declared file_size doesn't bypass this
                # in practice: Python's zipfile enforces file_size as a
                # hard cap during decompression and CRC-validates against
                # it, so a lying-small value fails fast below with a clean
                # BadZipFile -> ValueError instead of reading unbounded
                # decompressed data (verified empirically, not assumed).
                if info.file_size > MAX_UPLOAD_BYTES:
                    raise ValueError(
                        f"project.json inside the zip exceeds the "
                        f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit ({info.file_size} bytes declared)"
                    )
                raw = archive.read("project.json")
        except zipfile.BadZipFile as exc:
            raise ValueError(f"not a valid .qualilab zip file: {exc}") from exc
    else:
        raw = content

    try:
        return json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"could not parse .qualilab content as JSON: {exc}") from exc


def serialize_qualilab_project(original_content: bytes, project: dict) -> bytes:
    """Serialize `project` back to bytes in the same container shape
    `original_content` was read in: plain JSON stays plain JSON; a zip
    stays a zip, with every entry other than `project.json` (e.g.
    `pdfs/*.pdf`, `pdfindex/*.json`) carried through byte-for-byte,
    untouched -- this module never parses or generates PDF content."""
    project_json = json.dumps(project, ensure_ascii=False).encode("utf-8")
    if original_content[:2] != b"PK":
        return project_json

    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original_content)) as source:
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as dest:
            for item in source.infolist():
                data = project_json if item.filename == "project.json" else source.read(item.filename)
                dest.writestr(item, data)
    return buffer.getvalue()


def _project_categories(project: dict) -> list[dict]:
    """The fixture QualiLab ships as its own example uses `categories`,
    not `attributes` as its README currently documents -- read both,
    trust neither exclusively (finding #4)."""
    return project.get("categories") or project.get("attributes") or []


def qualilab_documents_to_records(project: dict, corpus_id: str) -> list[DocumentRecord]:
    """Map `documents[].{id, name, content}` to `DocumentRecord` rows,
    preserving QualiLab's own string id as `external_id` (finding #1) --
    a dedicated function, not a reuse of the CSV row-import path, because
    CSV rows have no stable id to preserve in the first place."""
    documents = project.get("documents") or []
    return [
        DocumentRecord(corpus_id=corpus_id, text=doc.get("content") or "", external_id=doc.get("id"))
        for doc in documents
    ]


@dataclass
class HumanLabelImportResult:
    accepted: list[HumanLabelRecord] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)  # [{document_external_id, value, reason}]
    coverage: dict = field(default_factory=dict)  # {documents_with_value, total_corpus_documents}

    @property
    def ok(self) -> bool:
        return not self.rejected


def qualilab_doc_values_to_human_labels(
    project: dict,
    category_id: str,
    codebook_id: int,
    documents: list[DocumentRecord],
    value_mapping: dict[str, str],
    valid_categories: set[str],
    layer: str = "final",
) -> HumanLabelImportResult:
    """Map `doc_values` entries for one `category_id`/`layer` into
    `HumanLabelRecord` rows, ready to insert.

    All-or-nothing on mapping validity (finding #6): if *any* present
    value has no `value_mapping` entry, or maps to something that isn't a
    real category of the target codebook, `accepted` comes back empty and
    every problem is in `rejected` -- nothing should be written on a
    partial result, since a silently smaller gold set is a *biased* one,
    not just a smaller one.

    Documents with no `doc_values` entry at all for this category/layer
    are not an error -- they're reflected in `coverage` instead (finding
    #11), consistent with this project's own acceptance of small, partial
    gold sets elsewhere (see TODO.md's V7 pilot notes).

    With `layer="final"`, more than one entry for the same document is
    treated as malformed input and raises `ValueError` outright (finding
    #14) -- QualiLab's own "final" layer is defined as the team's single
    consolidated answer, and this is what keeps that default import path
    safe for validation.py's agreement_report(), which assumes exactly
    one gold row per document.
    """
    # Without this, a mistyped category_id (or a .qualilab upload that
    # simply doesn't declare it) silently produces zero matches below,
    # and the caller gets back a "successful" HumanLabelImportResult with
    # ok=True and created_count=0 -- a false positive, since ok only
    # means "nothing was rejected", not "anything was imported".
    categories = _project_categories(project)
    if not any(c.get("id") == category_id for c in categories):
        raise ValueError(f"category {category_id!r} not found in the uploaded .qualilab file")

    doc_values = project.get("doc_values") or []
    external_id_to_document = {d.external_id: d for d in documents if d.external_id is not None}
    relevant = [v for v in doc_values if v.get("category_id") == category_id and v.get("layer") == layer]

    if layer == "final":
        seen: set = set()
        for entry in relevant:
            doc_id = entry.get("document_id")
            if doc_id in seen:
                raise ValueError(
                    f"malformed .qualilab file: more than one 'final' doc_values entry for document "
                    f"{doc_id!r}, category {category_id!r} -- 'final' is defined as the team's single "
                    "consolidated answer, so this file can't be trusted as a gold-standard source for "
                    "this category without being fixed in QualiLab first"
                )
            seen.add(doc_id)

    accepted: list[HumanLabelRecord] = []
    rejected: list[dict] = []
    # A set of document ids, not a running count -- on an "individual"
    # (multi-coder) layer, several entries share the same document_id, and
    # counting entries instead of distinct documents let coverage report
    # more "documents with a value" than the corpus actually has documents.
    documents_with_value_ids: set = set()

    for entry in relevant:
        document = external_id_to_document.get(entry.get("document_id"))
        if document is None:
            continue  # not part of this corpus (or this upload doesn't match it)

        raw_value = entry.get("value")
        if not raw_value:
            continue  # no answer recorded -- reflected in coverage below, not a rejection

        documents_with_value_ids.add(entry.get("document_id"))
        mapped = value_mapping.get(raw_value)
        if mapped is None:
            rejected.append(
                {"document_external_id": entry.get("document_id"), "value": raw_value,
                 "reason": f"value {raw_value!r} has no entry in value_mapping"}
            )
            continue
        if mapped not in valid_categories:
            rejected.append(
                {"document_external_id": entry.get("document_id"), "value": raw_value,
                 "reason": f"value_mapping maps {raw_value!r} to {mapped!r}, which is not a category "
                           f"of this codebook (expected one of {sorted(valid_categories)})"}
            )
            continue

        accepted.append(
            HumanLabelRecord(
                document_id=document.id,
                codebook_id=codebook_id,
                category=mapped,
                coder=entry.get("author_name") or entry.get("set_by") or "unknown",
                source="qualilab_import",
                layer=layer,
            )
        )

    if not documents_with_value_ids:
        # category_id is now known to exist (checked above), so zero
        # documents_with_value here means either this corpus's documents
        # have no matching external_id (e.g. a CSV/XLSX-imported corpus,
        # which has none at all) or this .qualilab file simply has no
        # doc_values for this category/layer -- either way, a "successful"
        # 0-row import is a no-op that shouldn't report ok=True.
        raise ValueError(
            f"no doc_values found for category {category_id!r}, layer {layer!r} that match this corpus's "
            "documents by external_id -- check the corpus was imported from this same .qualilab file"
        )

    return HumanLabelImportResult(
        accepted=accepted if not rejected else [],
        rejected=rejected,
        coverage={
            "documents_with_value": len(documents_with_value_ids),
            "total_corpus_documents": len(documents),
        },
    )


@dataclass
class QualilabExportResult:
    project: dict
    matched_count: int
    skipped_count: int


def inject_extractions_into_qualilab(
    project: dict,
    extractions: list[ExtractionRecord],
    documents: list[DocumentRecord],
    category_id: str,
    reverse_value_mapping: dict[str, str],
    run_id: int,
    model_label: str,
) -> QualilabExportResult:
    """Inject a run's extractions into `project` as new `doc_values`
    entries, returning the mutated dict (not yet re-serialized -- see
    `serialize_qualilab_project`) plus matched/skipped counts.

    Validates `category_id` and every extraction's mapped value against
    the target category's declared `options` *before* writing anything
    (finding #9) -- an unmatched value would render as a blank/unselected
    dropdown in QualiLab's own UI, silently making the export useless.

    Raises `ValueError` if zero documents match by `external_id` (finding
    #10) -- a corpus with no external ids (e.g. CSV-imported) or an
    unrelated `.qualilab` upload must not produce a no-op success.
    """
    categories = _project_categories(project)
    category = next((c for c in categories if c.get("id") == category_id), None)
    if category is None:
        raise ValueError(f"category {category_id!r} not found in the uploaded .qualilab file")
    valid_options = set(category.get("options") or [])

    for extraction in extractions:
        if extraction.category == ERROR_CATEGORY:
            # run_extraction deliberately records a per-document failure
            # (LLM timeout, malformed output after retries) as this
            # sentinel instead of aborting the whole run -- it was never a
            # real codebook category and was never going to be in
            # reverse_value_mapping, so validating it here would fail the
            # entire export over one bad document in an otherwise-good
            # 1000-document run. Skipped in the injection loop below
            # instead, same as an unmatched external_id.
            continue
        mapped = reverse_value_mapping.get(extraction.category)
        if mapped is None or (valid_options and mapped not in valid_options):
            raise ValueError(
                f"category {extraction.category!r} maps (via reverse_value_mapping) to {mapped!r}, "
                f"which is not a declared option of category {category_id!r} "
                f"(options: {sorted(valid_options)})"
            )

    document_by_id = {d.id: d for d in documents}
    doc_values = list(project.get("doc_values") or [])

    matched = 0
    skipped = 0
    for extraction in extractions:
        if extraction.category == ERROR_CATEGORY:
            skipped += 1
            continue
        document = document_by_id.get(extraction.document_id)
        if document is None or document.external_id is None:
            skipped += 1
            continue

        entry_id = f"cifra-{run_id}-{document.external_id}-{category_id}"
        # Upsert, not append: drop any existing entry with this exact id
        # first. A bare append would duplicate on re-export (finding #13 --
        # a deterministic id alone doesn't cause replacement; this step is
        # what makes re-exporting the same run idempotent instead of just
        # asserted to be).
        doc_values = [entry for entry in doc_values if entry.get("id") != entry_id]
        doc_values.append(
            {
                "id": entry_id,
                "document_id": document.external_id,
                "category_id": category_id,
                "value": reverse_value_mapping[extraction.category],
                "set_by": None,  # not a string (finding #8): QualiLab expects a real user id or null
                "author_name": f"Decifra ({model_label})",
                "layer": "individual",
            }
        )
        matched += 1

    if matched == 0:
        raise ValueError("zero documents matched by external_id -- nothing to export")

    project = {**project, "doc_values": doc_values}
    return QualilabExportResult(project=project, matched_count=matched, skipped_count=skipped)
