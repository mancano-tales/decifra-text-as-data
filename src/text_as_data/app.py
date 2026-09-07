from __future__ import annotations

import json
from datetime import datetime
from threading import Lock
from typing import Literal

import pandas as pd
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import Session, delete, select

from .codebook import spec_from_yaml_string, spec_to_yaml_string
from .corpus_import import parse_csv_rows, parse_docx_bytes, parse_pdf_bytes, parse_txt_bytes, parse_xlsx_rows
from .db import CodebookRecord, DocumentRecord, ExtractionRecord, HumanLabelRecord, RunRecord, get_engine
from .disclosure import build_disclosure
from .export import results_to_csv_bytes, results_to_json_bytes, results_to_xlsx_bytes
from .extraction import run_extraction
from .providers import CliProvider, Provider, make_api_key_provider
from .validation import agreement_report, reproducibility_report
from .qualilab_interop import (
    inject_extractions_into_qualilab,
    open_qualilab_project,
    qualilab_documents_to_records,
    qualilab_doc_values_to_human_labels,
    serialize_qualilab_project,
)

_EXPORT_CONTENT_TYPES = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "json": "application/json",
}
_EXPORT_BUILDERS = {
    "csv": results_to_csv_bytes,
    "xlsx": results_to_xlsx_bytes,
    "json": results_to_json_bytes,
}

app = FastAPI(title="Decifra backend (Slice 1)")

app.add_middleware(
    CORSMiddleware,
    # A fixed single origin (":5173") breaks the moment two dev frontends
    # run at once on different ports -- a real scenario, not hypothetical,
    # once multiple people/sessions work on this repo locally. Any
    # localhost/127.0.0.1 origin on any port is allowed instead; this is a
    # local dev backend, not a deployed one, so there's no production
    # origin to restrict against.
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_methods=["*"],
    allow_headers=["*"],
)

# Importing the API must not create or migrate the user's database. Tests
# override this dependency; runtime initializes it once, on first use.
_engine = None
_engine_lock = Lock()


def get_engine_dependency():
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = get_engine()
        return _engine


class CreateRunRequest(BaseModel):
    codebook_id: int
    corpus_id: str
    model: str
    provider_mode: Literal["api_key", "cli"] = "api_key"
    cli_command: list[str] | None = None
    cli_prompt_mode: Literal["stdin", "arg"] = "stdin"
    # Set true to verify reproducibility: re-run against the same
    # codebook/corpus/model as an earlier run without serving that run's
    # cached extractions back. See GET /runs/{run_id}/reproducibility.
    bypass_cache: bool = False


_MODEL_PREFIX_TO_VENDOR = {
    "claude": "anthropic",
    "gpt": "openai",
    "o1": "openai",
    "o3": "openai",
}


def _vendor_for_model(model: str) -> str:
    """Infer the `instructor` vendor from a model name's own prefix (e.g.
    `claude-haiku-4-5` -> `anthropic`, `gpt-4o` -> `openai`) instead of a
    hardcoded constant -- a request for a non-Anthropic model must not
    silently be sent to the Anthropic API with an invalid model name."""
    for prefix, vendor in _MODEL_PREFIX_TO_VENDOR.items():
        if model.startswith(prefix):
            return vendor
    raise HTTPException(
        status_code=422,
        detail=f"could not infer an API vendor for model {model!r}; "
        f"expected a model name starting with one of {sorted(_MODEL_PREFIX_TO_VENDOR)}",
    )


def get_provider_dependency(request: CreateRunRequest) -> Provider:
    """Built from the request's own `model` (and, for CLI mode, its own
    `cli_command`/`cli_prompt_mode`) -- not a hardcoded constant. The model
    actually invoked must match what's persisted on the `RunRecord` and
    used as the cache key in `run_extraction`, or both become misleading.

    CLI mode is the agent-agnostic path documented in AGENTS.md's provider
    layer design: any already-installed CLI that accepts a prompt and
    returns text works here, not just `claude -p` -- e.g. Google
    Antigravity's `agy -p "<prompt>"`, which (unlike `claude -p`) requires
    the prompt as a trailing argument rather than reading stdin, hence
    `cli_prompt_mode`."""
    if request.provider_mode == "cli":
        if not request.cli_command:
            raise HTTPException(status_code=422, detail="cli_command is required when provider_mode is 'cli'")
        return CliProvider(command=request.cli_command, prompt_mode=request.cli_prompt_mode)
    return make_api_key_provider(vendor=_vendor_for_model(request.model), model=request.model)


@app.get("/runs")
def list_runs(engine=Depends(get_engine_dependency)):
    with Session(engine) as session:
        runs = session.exec(select(RunRecord).order_by(RunRecord.created_at.desc())).all()
        results = []
        for run in runs:
            codebook = session.get(CodebookRecord, run.codebook_id)
            total = len(
                session.exec(select(DocumentRecord).where(DocumentRecord.corpus_id == run.corpus_id)).all()
            )
            processed = len(session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == run.id)).all())
            results.append(
                {
                    "id": run.id,
                    "corpus_id": run.corpus_id,
                    "codebook_id": run.codebook_id,
                    "codebook_name": codebook.name if codebook else None,
                    "model": run.model,
                    "status": run.status,
                    "processed": processed,
                    "total": total,
                    "created_at": run.created_at,
                }
            )
        return results


@app.post("/runs")
def create_run(
    request: CreateRunRequest,
    background_tasks: BackgroundTasks,
    engine=Depends(get_engine_dependency),
    provider: Provider = Depends(get_provider_dependency),
):
    with Session(engine) as session:
        codebook = session.get(CodebookRecord, request.codebook_id)
        if codebook is None:
            raise HTTPException(status_code=404, detail=f"codebook {request.codebook_id} not found")

        corpus_exists = session.exec(
            select(DocumentRecord).where(DocumentRecord.corpus_id == request.corpus_id)
        ).first()
        if corpus_exists is None:
            raise HTTPException(status_code=404, detail=f"corpus {request.corpus_id!r} not found")

        provider_detail = (
            " ".join(request.cli_command) if request.provider_mode == "cli" and request.cli_command else request.model
        )
        run = RunRecord(
            codebook_id=request.codebook_id,
            corpus_id=request.corpus_id,
            model=request.model,
            provider_mode=request.provider_mode,
            provider_detail=provider_detail,
            bypass_cache=request.bypass_cache,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id

    background_tasks.add_task(run_extraction, engine, run_id, provider)
    return {"run_id": run_id}


@app.get("/runs/{run_id}")
def get_run(run_id: int, engine=Depends(get_engine_dependency)):
    with Session(engine) as session:
        run = session.get(RunRecord, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")

        total = len(session.exec(select(DocumentRecord).where(DocumentRecord.corpus_id == run.corpus_id)).all())
        processed = len(session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == run_id)).all())
        return {"id": run.id, "status": run.status, "processed": processed, "total": total}


def _extraction_with_snippet(session: Session, extraction: ExtractionRecord) -> dict:
    document = session.get(DocumentRecord, extraction.document_id)
    snippet = document.text[:160] if document else ""
    return {**extraction.model_dump(), "document_snippet": snippet}


_SQLITE_MAX_IN_CLAUSE = 500


def _extractions_with_snippets(session: Session, extractions: list[ExtractionRecord]) -> list[dict]:
    """Batch version of `_extraction_with_snippet` -- one query for every
    document a run's extractions reference, instead of one query per row.
    A single-row helper is fine for `update_extraction`, but the results
    and export endpoints list every row in a run, where a per-row lookup
    turns into N+1 queries as a run grows.

    Chunked into batches of `_SQLITE_MAX_IN_CLAUSE` ids -- SQLite's default
    build caps a statement at 999 bound parameters (SQLITE_MAX_VARIABLE_NUMBER),
    so a single `IN (...)` over a run with more than ~999 distinct documents
    would raise `sqlite3.OperationalError: too many SQL variables`."""
    document_ids = list({e.document_id for e in extractions})
    documents = []
    for i in range(0, len(document_ids), _SQLITE_MAX_IN_CLAUSE):
        chunk = document_ids[i : i + _SQLITE_MAX_IN_CLAUSE]
        documents.extend(session.exec(select(DocumentRecord).where(DocumentRecord.id.in_(chunk))).all())
    snippets = {d.id: d.text[:160] for d in documents}
    return [{**e.model_dump(), "document_snippet": snippets.get(e.document_id, "")} for e in extractions]


@app.get("/runs/{run_id}/results")
def get_run_results(run_id: int, engine=Depends(get_engine_dependency)):
    with Session(engine) as session:
        run = session.get(RunRecord, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")

        rows = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == run_id)).all()
        return _extractions_with_snippets(session, rows)


class UpdateExtractionRequest(BaseModel):
    categoria: str
    justificativa: str


@app.put("/runs/{run_id}/results/{extraction_id}")
def update_extraction(
    run_id: int, extraction_id: int, request: UpdateExtractionRequest, engine=Depends(get_engine_dependency)
):
    with Session(engine) as session:
        run = session.get(RunRecord, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")

        extraction = session.get(ExtractionRecord, extraction_id)
        if extraction is None or extraction.run_id != run_id:
            raise HTTPException(status_code=404, detail=f"extraction {extraction_id} not found in run {run_id}")

        codebook = session.get(CodebookRecord, run.codebook_id)
        valid_labels = {c["label"] for c in spec_from_yaml_string(codebook.yaml_raw)["categories"]}
        if request.categoria not in valid_labels:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"categoria {request.categoria!r} is not a valid label for this codebook; "
                    f"expected one of {sorted(valid_labels)}"
                ),
            )

        extraction.categoria = request.categoria
        extraction.justificativa = request.justificativa
        session.add(extraction)
        session.commit()
        session.refresh(extraction)
        return _extraction_with_snippet(session, extraction)


@app.post("/runs/{run_id}/gold-labels")
async def upload_gold_labels(run_id: int, file: UploadFile = File(...), engine=Depends(get_engine_dependency)):
    """Upload hand-reviewed gold labels for a run, from a CSV shaped like
    `GET /runs/{run_id}/export?format=csv`'s own output plus one more
    column: `gold_categoria` (blank for rows not yet reviewed). All-or-
    nothing on validity -- a non-blank value that isn't one of the
    codebook's real category labels rejects the whole upload with every
    bad row listed, since a silently-accepted typo would corrupt the gold
    set for every future validation report against this codebook."""
    with Session(engine) as session:
        run = session.get(RunRecord, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")

        codebook = session.get(CodebookRecord, run.codebook_id)
        valid_labels = {c["label"] for c in spec_from_yaml_string(codebook.yaml_raw)["categories"]}

    content = await file.read()
    try:
        rows = parse_csv_rows(content)
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"could not decode file as UTF-8: {exc}") from exc
    if not rows or "document_id" not in rows[0] or "gold_categoria" not in rows[0]:
        raise HTTPException(
            status_code=422,
            detail="file must have 'document_id' and 'gold_categoria' columns "
            "(export a run's results and add a gold_categoria column to it)",
        )

    to_import: list[tuple[int, str]] = []
    skipped_blank = 0
    bad_rows: list[str] = []
    for row in rows:
        value = (row.get("gold_categoria") or "").strip()
        if not value:
            skipped_blank += 1
            continue
        if value not in valid_labels:
            bad_rows.append(f"document_id {row['document_id']}: {value!r} is not a valid category")
            continue
        try:
            document_id = int(row["document_id"])
        except (TypeError, ValueError):
            bad_rows.append(f"document_id {row['document_id']!r} is not a valid integer")
            continue
        to_import.append((document_id, value))

    if bad_rows:
        raise HTTPException(
            status_code=422,
            detail=f"expected one of {sorted(valid_labels)}; problems found: " + "; ".join(bad_rows),
        )

    with Session(engine) as session:
        # Replace, not append: the design spec expects re-uploads as
        # coverage grows over time, not a one-shot action -- without this,
        # re-uploading a correction for a document already manually
        # labeled would insert a second HumanLabelRecord for it, and the
        # validation report would then wrongly exclude that document as
        # "multi-coder" instead of using the corrected value.
        imported_document_ids = {document_id for document_id, _ in to_import}
        if imported_document_ids:
            session.exec(
                delete(HumanLabelRecord).where(
                    HumanLabelRecord.codebook_id == run.codebook_id,
                    HumanLabelRecord.source == "manual",
                    HumanLabelRecord.document_id.in_(imported_document_ids),
                )
            )
        for document_id, category in to_import:
            session.add(
                HumanLabelRecord(
                    document_id=document_id,
                    codebook_id=run.codebook_id,
                    category=category,
                    coder="manual",
                    source="manual",
                )
            )
        session.commit()

    return {"imported": len(to_import), "skipped_blank": skipped_blank}


@app.get("/runs/{run_id}/validation")
def get_run_validation(run_id: int, engine=Depends(get_engine_dependency)):
    """Compare a run's extractions against hand-reviewed gold labels
    (uploaded via `POST /runs/{run_id}/gold-labels`) -- coverage, per-
    category accuracy/kappa/precision/recall/F1, and a disagreement list.
    A document with more than one gold row (e.g. a QualiLab "individual"-
    layer import with multiple coders) is excluded and counted, not
    silently resolved to one value -- picking or aggregating across
    coders is a validation-methodology decision this endpoint doesn't
    make on the researcher's behalf."""
    with Session(engine) as session:
        run = session.get(RunRecord, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")

        extractions = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == run_id)).all()
        total_documents = len(
            session.exec(select(DocumentRecord).where(DocumentRecord.corpus_id == run.corpus_id)).all()
        )
        gold_rows = session.exec(
            select(HumanLabelRecord).where(HumanLabelRecord.codebook_id == run.codebook_id)
        ).all()

        gold_by_document: dict[int, list[str]] = {}
        for row in gold_rows:
            gold_by_document.setdefault(row.document_id, []).append(row.category)

        single_gold: dict[int, str] = {}
        excluded_multi_coder = 0
        for document_id, categories in gold_by_document.items():
            if len(categories) > 1:
                excluded_multi_coder += 1
                continue
            single_gold[document_id] = categories[0]

        predicted_rows = [
            {"id": e.document_id, "categoria": e.categoria} for e in extractions if e.document_id in single_gold
        ]

        if not predicted_rows:
            return {
                "coverage": {
                    "labeled": len(single_gold),
                    "total": total_documents,
                    "excluded_multi_coder": excluded_multi_coder,
                },
                "per_category": {},
                "disagreements": [],
            }

        predicted_document_ids = {row["id"] for row in predicted_rows}
        gold_df_rows = [
            {"id": doc_id, "categoria": cat}
            for doc_id, cat in single_gold.items()
            if doc_id in predicted_document_ids
        ]

        predicted_df = pd.DataFrame(predicted_rows)
        gold_df = pd.DataFrame(gold_df_rows)
        report = agreement_report(predicted_df, gold_df, id_col="id", columns=["categoria"])
        metrics = report["per_column"]["categoria"]

        extraction_by_document = {e.document_id: e for e in extractions}
        disagreements = []
        for mismatch in report["mismatches"]:
            document_id = mismatch["id"]
            extraction = extraction_by_document[document_id]
            document = session.get(DocumentRecord, document_id)
            disagreements.append(
                {
                    "document_id": document_id,
                    "document_snippet": document.text[:160] if document else "",
                    "predicted": mismatch["predicted"],
                    "gold": mismatch["gold"],
                }
            )

        return {
            "coverage": {
                "labeled": len(single_gold),
                "total": total_documents,
                "excluded_multi_coder": excluded_multi_coder,
            },
            "per_category": metrics,
            "disagreements": disagreements,
        }


@app.get("/runs/{run_id}/export")
def export_run_results(
    run_id: int, format: Literal["csv", "xlsx", "json"] = "csv", engine=Depends(get_engine_dependency)
):
    with Session(engine) as session:
        run = session.get(RunRecord, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")

        rows = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == run_id)).all()
        result_rows = _extractions_with_snippets(session, rows)

    content = _EXPORT_BUILDERS[format](result_rows)
    return Response(
        content=content,
        media_type=_EXPORT_CONTENT_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="run_{run_id}_results.{format}"'},
    )


@app.get("/runs/{run_id}/disclosure")
def get_run_disclosure(run_id: int, engine=Depends(get_engine_dependency)):
    """GUIDE-LLM-shaped AI-use disclosure report for one run -- see
    disclosure.py's docstring for what this covers and why. Read-only,
    derived entirely from what's already persisted (RunRecord,
    ExtractionRecord, the codebook); nothing new to fill in by hand."""
    with Session(engine) as session:
        run = session.get(RunRecord, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")
        return build_disclosure(session, run)


@app.get("/runs/{run_id}/reproducibility")
def get_run_reproducibility(run_id: int, compare_to: int, engine=Depends(get_engine_dependency)):
    """Compare two completed runs against each other to measure whether
    the pipeline's own output is reproducible -- same codebook/corpus/
    model, does the LLM say the same thing twice? `compare_to` is
    typically a second run created with `bypass_cache: true` against the
    same config as `run_id`, so it actually re-queries the provider
    instead of replaying `run_id`'s cached answers back at itself."""
    with Session(engine) as session:
        run_a = session.get(RunRecord, run_id)
        if run_a is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")
        run_b = session.get(RunRecord, compare_to)
        if run_b is None:
            raise HTTPException(status_code=404, detail=f"run {compare_to} not found")

        if (run_a.codebook_id, run_a.corpus_id, run_a.model) != (run_b.codebook_id, run_b.corpus_id, run_b.model):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"runs {run_id} and {compare_to} aren't a same-configuration repeat "
                    "(codebook_id, corpus_id, and model must all match) -- comparing them would "
                    "measure 'are these two different setups different', not reproducibility"
                ),
            )
        if run_a.codebook_yaml_hash and run_b.codebook_yaml_hash and run_a.codebook_yaml_hash != run_b.codebook_yaml_hash:
            raise HTTPException(
                status_code=422,
                detail=f"runs {run_id} and {compare_to} used different codebook content -- "
                "the codebook was edited in place between them",
            )

        extractions_a = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == run_id)).all()
        extractions_b = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == compare_to)).all()

    if not extractions_a or not extractions_b:
        raise HTTPException(status_code=422, detail="both runs must have at least one extraction to compare")

    df_a = pd.DataFrame([{"document_id": e.document_id, "categoria": e.categoria} for e in extractions_a])
    df_b = pd.DataFrame([{"document_id": e.document_id, "categoria": e.categoria} for e in extractions_b])

    try:
        report = reproducibility_report(df_a, df_b, id_col="document_id", columns=["categoria"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {"run_a": run_id, "run_b": compare_to, **report}


class PasteCorpusRequest(BaseModel):
    name: str
    text: str


def _create_documents_or_409(engine, name: str, texts: list[str]) -> dict:
    with Session(engine) as session:
        existing = session.exec(select(DocumentRecord).where(DocumentRecord.corpus_id == name)).first()
        if existing is not None:
            raise HTTPException(status_code=409, detail=f"corpus {name!r} already exists")

        inserted = 0
        for text in texts:
            if text:
                session.add(DocumentRecord(corpus_id=name, text=text))
                inserted += 1
        if inserted == 0:
            # Every text was empty (e.g. a CSV/XLSX whose text_column was
            # blank on every row). Without this, the request "succeeds"
            # with document_count: 0 -- but since a corpus is defined
            # purely by having DocumentRecord rows with this corpus_id
            # (there's no separate corpora table), that "success" creates
            # nothing: GET /corpora won't list it, GET
            # /corpora/{id}/documents 404s, and POST /runs 404s too. A
            # 200 claiming success for an operation that had no effect is
            # worse than a clear rejection upfront.
            raise HTTPException(status_code=400, detail="every row/text was empty -- no documents to import")
        session.commit()

    return {"corpus_id": name, "document_count": inserted}


@app.post("/corpora/paste")
def create_corpus_from_paste(request: PasteCorpusRequest, engine=Depends(get_engine_dependency)):
    return _create_documents_or_409(engine, request.name, [request.text])


def _rows_to_texts(rows: list[dict], text_column: str) -> list[str]:
    if not rows:
        raise HTTPException(status_code=400, detail="file has no data rows")
    if text_column not in rows[0]:
        # csv.DictReader collects any columns beyond the header count under
        # a `None` key (its `restkey`, for a data row with more fields than
        # the header) -- sorting a mix of `str` and `None` raises a raw
        # TypeError instead of this 422, so `None` is filtered out here.
        available = sorted(k for k in rows[0].keys() if k is not None)
        raise HTTPException(
            status_code=422,
            detail=f"column {text_column!r} not found; available columns: {available}",
        )
    # `is not None` and a stripped non-empty check, not bare truthiness --
    # `row.get(text_column)` is falsy for a legitimate numeric `0`/`0.0`
    # cell (openpyxl returns XLSX numeric cells as int/float, not str),
    # and a bare `if row.get(text_column)` silently dropped those rows.
    return [
        str(row[text_column])
        for row in rows
        if row.get(text_column) is not None and str(row[text_column]).strip() != ""
    ]


@app.post("/corpora/csv")
async def create_corpus_from_csv(
    name: str = Form(...),
    text_column: str = Form(...),
    file: UploadFile = File(...),
    engine=Depends(get_engine_dependency),
):
    content = await file.read()
    try:
        rows = parse_csv_rows(content)
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"could not decode file as UTF-8: {exc}") from exc
    texts = _rows_to_texts(rows, text_column)
    return _create_documents_or_409(engine, name, texts)


@app.post("/corpora/xlsx")
async def create_corpus_from_xlsx(
    name: str = Form(...),
    text_column: str = Form(...),
    file: UploadFile = File(...),
    engine=Depends(get_engine_dependency),
):
    content = await file.read()
    try:
        rows = parse_xlsx_rows(content)
    except Exception as exc:  # noqa: BLE001 -- any openpyxl parse failure means "not a valid xlsx"
        raise HTTPException(status_code=400, detail=f"could not parse file as XLSX: {exc}") from exc
    texts = _rows_to_texts(rows, text_column)
    return _create_documents_or_409(engine, name, texts)


_DOCUMENT_PARSERS = {
    "txt": parse_txt_bytes,
    "md": parse_txt_bytes,
    "docx": parse_docx_bytes,
    "pdf": parse_pdf_bytes,
}


@app.post("/corpora/documents")
async def create_corpus_from_documents(
    name: str = Form(...), files: list[UploadFile] = File(...), engine=Depends(get_engine_dependency)
):
    """Import standalone TXT/MD/DOCX/PDF files as a corpus -- one uploaded
    file is one document, unlike CSV/XLSX's one-row-is-one-document. A
    mixed batch (some .txt, some .pdf) is fine; each file is dispatched by
    its own extension. All-or-nothing on parse failures, matching the
    CSV/XLSX endpoints' convention: one bad file fails the whole request
    rather than silently importing a partial corpus."""
    records: list[DocumentRecord] = []
    for upload in files:
        extension = (upload.filename or "").rsplit(".", 1)[-1].lower()
        parser = _DOCUMENT_PARSERS.get(extension)
        if parser is None:
            raise HTTPException(
                status_code=422,
                detail=f"{upload.filename!r}: unsupported file type {extension!r} "
                f"(expected one of {sorted(_DOCUMENT_PARSERS)})",
            )
        content = await upload.read()
        try:
            text = parser(content)
        except Exception as exc:  # noqa: BLE001 -- any parser failure means "not a valid <type> file"
            raise HTTPException(
                status_code=400, detail=f"could not parse {upload.filename!r} as .{extension}: {exc}"
            ) from exc
        records.append(
            DocumentRecord(
                corpus_id=name, text=text, metadata_json=json.dumps({"filename": upload.filename})
            )
        )

    return _create_document_records_or_409(engine, name, records)


def _create_document_records_or_409(engine, name: str, records: list[DocumentRecord]) -> dict:
    """Sibling of `_create_documents_or_409` for sources that supply whole
    `DocumentRecord`s (with `external_id` already set) rather than bare
    strings -- currently only the QualiLab import path."""
    with Session(engine, expire_on_commit=False) as session:
        existing = session.exec(select(DocumentRecord).where(DocumentRecord.corpus_id == name)).first()
        if existing is not None:
            raise HTTPException(status_code=409, detail=f"corpus {name!r} already exists")

        inserted = []
        for record in records:
            if record.text:
                record.corpus_id = name
                session.add(record)
                inserted.append(record)
        if not inserted:
            # Same reasoning as _create_documents_or_409: with no separate
            # corpora table, a 0-document "success" here creates a corpus
            # name that's invisible everywhere else (GET /corpora, POST
            # /runs) -- e.g. every uploaded file was blank, or a QualiLab
            # project's documents[] all had empty content.
            raise HTTPException(status_code=400, detail="every document was empty -- no documents to import")
        session.commit()
        for record in inserted:
            session.refresh(record)

        return {
            "corpus_id": name,
            "document_count": len(inserted),
            "documents": [{"id": r.id, "external_id": r.external_id} for r in inserted],
        }


@app.post("/corpora/import-qualilab")
async def create_corpus_from_qualilab(
    name: str = Form(...), file: UploadFile = File(...), engine=Depends(get_engine_dependency)
):
    content = await file.read()
    try:
        project = open_qualilab_project(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    records = qualilab_documents_to_records(project, corpus_id=name)
    return _create_document_records_or_409(engine, name, records)


def _parse_json_object_form_field(field_name: str, raw: str) -> dict:
    """Parse a form field expected to be a JSON object (e.g.
    value_mapping/reverse_value_mapping), rejecting anything that parses
    as valid JSON but isn't an object -- `json.loads("[1,2,3]")` or
    `json.loads("true")` succeed without raising, and the caller
    immediately does `.get(...)` on the result, which would otherwise
    raise a raw AttributeError instead of a clean 400."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=400, detail=f"{field_name} must be a JSON object, got {type(parsed).__name__}"
        )
    return parsed


@app.post("/corpora/{corpus_id}/import-qualilab-labels")
async def import_qualilab_labels(
    corpus_id: str,
    codebook_id: int = Form(...),
    category_id: str = Form(...),
    value_mapping: str = Form(...),  # JSON object, QualiLab option text -> codebook category label
    layer: str = Form("final"),
    file: UploadFile = File(...),
    engine=Depends(get_engine_dependency),
):
    content = await file.read()
    try:
        project = open_qualilab_project(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    parsed_mapping = _parse_json_object_form_field("value_mapping", value_mapping)

    with Session(engine) as session:
        codebook = session.get(CodebookRecord, codebook_id)
        if codebook is None:
            raise HTTPException(status_code=404, detail=f"codebook {codebook_id} not found")
        valid_categories = {c["label"] for c in spec_from_yaml_string(codebook.yaml_raw)["categories"]}

        documents = session.exec(select(DocumentRecord).where(DocumentRecord.corpus_id == corpus_id)).all()
        if not documents:
            raise HTTPException(status_code=404, detail=f"corpus {corpus_id!r} not found")

        try:
            result = qualilab_doc_values_to_human_labels(
                project,
                category_id=category_id,
                codebook_id=codebook_id,
                documents=documents,
                value_mapping=parsed_mapping,
                valid_categories=valid_categories,
                layer=layer,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if not result.ok:
            raise HTTPException(
                status_code=422,
                detail={"message": "one or more doc_values could not be mapped to a codebook category", "problems": result.rejected},
            )

        # Replace, not append: re-running this same import (e.g. after
        # fixing a mismapped value in the .qualilab file) would otherwise
        # insert a second HumanLabelRecord for every document already
        # imported under this (codebook_id, layer), silently violating
        # agreement_report()'s one-gold-row-per-document precondition.
        accepted_document_ids = {label.document_id for label in result.accepted}
        if accepted_document_ids:
            session.exec(
                delete(HumanLabelRecord).where(
                    HumanLabelRecord.codebook_id == codebook_id,
                    HumanLabelRecord.layer == layer,
                    HumanLabelRecord.document_id.in_(accepted_document_ids),
                )
            )
        for label in result.accepted:
            session.add(label)
        session.commit()

        return {"created_count": len(result.accepted), "coverage": result.coverage}


@app.post("/runs/{run_id}/export-qualilab")
async def export_run_to_qualilab(
    run_id: int,
    category_id: str = Form(...),
    reverse_value_mapping: str = Form(...),  # JSON object, codebook category label -> QualiLab option text
    file: UploadFile = File(...),
    engine=Depends(get_engine_dependency),
):
    content = await file.read()
    try:
        project = open_qualilab_project(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    parsed_mapping = _parse_json_object_form_field("reverse_value_mapping", reverse_value_mapping)

    with Session(engine) as session:
        run = session.get(RunRecord, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")

        extractions = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == run_id)).all()
        documents = session.exec(select(DocumentRecord).where(DocumentRecord.corpus_id == run.corpus_id)).all()

        try:
            result = inject_extractions_into_qualilab(
                project,
                extractions=extractions,
                documents=documents,
                category_id=category_id,
                reverse_value_mapping=parsed_mapping,
                run_id=run_id,
                model_label=run.model,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    output = serialize_qualilab_project(content, result.project)
    media_type = "application/zip" if content[:2] == b"PK" else "application/json"
    return Response(
        content=output,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="run_{run_id}_export.qualilab"',
            "X-Decifra-Matched-Count": str(result.matched_count),
            "X-Decifra-Skipped-Count": str(result.skipped_count),
        },
    )


@app.get("/corpora")
def list_corpora(engine=Depends(get_engine_dependency)):
    with Session(engine) as session:
        documents = session.exec(select(DocumentRecord).order_by(DocumentRecord.id)).all()

    counts: dict[str, int] = {}
    first_created_at: dict[str, datetime] = {}
    for doc in documents:
        counts[doc.corpus_id] = counts.get(doc.corpus_id, 0) + 1
        first_created_at.setdefault(doc.corpus_id, doc.created_at)

    ordered = sorted(counts, key=lambda corpus_id: first_created_at[corpus_id])
    return [{"corpus_id": cid, "document_count": counts[cid]} for cid in ordered]


@app.get("/corpora/{corpus_id}/documents")
def list_corpus_documents(
    corpus_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    engine=Depends(get_engine_dependency),
):
    with Session(engine) as session:
        total = len(session.exec(select(DocumentRecord).where(DocumentRecord.corpus_id == corpus_id)).all())
        if total == 0:
            raise HTTPException(status_code=404, detail=f"corpus {corpus_id!r} not found")

        documents = session.exec(
            select(DocumentRecord)
            .where(DocumentRecord.corpus_id == corpus_id)
            .order_by(DocumentRecord.id)
            .offset(offset)
            .limit(limit)
        ).all()
        return [d.model_dump() for d in documents]


class CategorySpec(BaseModel):
    label: str
    definition: str
    positive_examples: list[str] = []
    negative_examples: list[str] = []
    boundary_notes: str = ""


class CodebookSpecRequest(BaseModel):
    concept: str
    description: str
    categories: list[CategorySpec]


@app.post("/codebooks")
def create_codebook(request: CodebookSpecRequest, engine=Depends(get_engine_dependency)):
    spec = request.model_dump()
    try:
        yaml_raw = spec_to_yaml_string(spec)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    with Session(engine) as session:
        record = CodebookRecord(name=request.concept, yaml_raw=yaml_raw)
        session.add(record)
        session.commit()
        session.refresh(record)
        return {"id": record.id, "name": record.name}


@app.get("/codebooks")
def list_codebooks(engine=Depends(get_engine_dependency)):
    with Session(engine) as session:
        records = session.exec(select(CodebookRecord).order_by(CodebookRecord.created_at)).all()
        return [{"id": r.id, "name": r.name, "created_at": r.created_at} for r in records]


@app.get("/codebooks/{codebook_id}")
def get_codebook(codebook_id: int, engine=Depends(get_engine_dependency)):
    with Session(engine) as session:
        record = session.get(CodebookRecord, codebook_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"codebook {codebook_id} not found")
        return {
            "id": record.id,
            "name": record.name,
            "spec": spec_from_yaml_string(record.yaml_raw),
            "yaml_raw": record.yaml_raw,
        }


@app.put("/codebooks/{codebook_id}")
def update_codebook(codebook_id: int, request: CodebookSpecRequest, engine=Depends(get_engine_dependency)):
    spec = request.model_dump()
    try:
        yaml_raw = spec_to_yaml_string(spec)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    with Session(engine) as session:
        record = session.get(CodebookRecord, codebook_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"codebook {codebook_id} not found")
        record.name = request.concept
        record.yaml_raw = yaml_raw
        session.add(record)
        session.commit()
        return {"id": record.id, "name": record.name}
