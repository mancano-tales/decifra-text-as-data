"""Tests for qualilab_interop.py, run against a copy of QualiLab's own
shipped example fixture (tests/fixtures/QualiLab_synthetic_realistic_legal_ai_3.qualilab,
from github.com/luizpf42/QualiLab, MIT license) wherever real project shape
matters, and small synthetic projects where a specific edge case needs full
control. See docs/superpowers/specs/2026-09-02-qualilab-interop-design.md
for the design and the findings each behavior traces back to."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from text_as_data.db import DocumentRecord, ExtractionRecord
from text_as_data import qualilab_interop as interop

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "QualiLab_synthetic_realistic_legal_ai_3.qualilab"
FIXTURE_BYTES = FIXTURE_PATH.read_bytes()


def _fixture_project() -> dict:
    return interop.open_qualilab_project(FIXTURE_BYTES)


# ---------------------------------------------------------------------------
# open_qualilab_project
# ---------------------------------------------------------------------------


def test_open_qualilab_project_parses_the_real_fixture():
    project = _fixture_project()

    assert "documents" in project
    assert "doc_values" in project
    assert "codings" in project
    assert len(project["documents"]) == 9


def test_open_qualilab_project_rejects_oversized_raw_upload(monkeypatch):
    monkeypatch.setattr(interop, "MAX_UPLOAD_BYTES", 10)

    with pytest.raises(ValueError, match="exceeds"):
        interop.open_qualilab_project(b'{"documents": []}')


def test_open_qualilab_project_rejects_malformed_json():
    with pytest.raises(ValueError, match="could not parse"):
        interop.open_qualilab_project(b"{not valid json")


def test_open_qualilab_project_reads_a_zip_container():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("project.json", json.dumps({"documents": [{"id": "doc-1", "content": "hi"}]}))

    project = interop.open_qualilab_project(buffer.getvalue())

    assert project["documents"][0]["id"] == "doc-1"


def test_open_qualilab_project_rejects_zip_with_oversized_project_json_entry(monkeypatch):
    monkeypatch.setattr(interop, "MAX_UPLOAD_BYTES", 10)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("project.json", json.dumps({"documents": [{"id": "doc-1", "content": "x" * 100}]}))

    # Caught via the zip's own declared file_size, before ever calling
    # .read() on the entry -- a genuine zip-bomb defense, not just a
    # post-hoc size check (finding #3).
    with pytest.raises(ValueError, match="exceeds"):
        interop.open_qualilab_project(buffer.getvalue())


def test_open_qualilab_project_fails_cleanly_on_a_zip_with_a_lied_smaller_file_size(monkeypatch):
    # A round-2 adversarial review raised this as a potential zip-bomb
    # bypass: `info.file_size` is client-supplied central-directory
    # metadata, and open_qualilab_project's own size check only compares
    # against it, not against what actually comes out of read(). Verified
    # empirically (not assumed) that this isn't actually exploitable
    # against Python's zipfile: ZipExtFile.read() enforces file_size as a
    # hard cap during decompression and CRC-validates against it, so a
    # lied-smaller value doesn't let more decompressed bytes through --
    # it just fails fast with BadZipFile, which the existing except
    # clause already turns into a clean ValueError. This test locks in
    # that verified-safe behavior.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("project.json", json.dumps({"documents": [{"id": "doc-1", "content": "x" * 50000}]}))

    original_getinfo = zipfile.ZipFile.getinfo

    def _lying_getinfo(self, name):
        info = original_getinfo(self, name)
        info.file_size = 10  # lies: understates the real ~50KB decompressed size
        return info

    monkeypatch.setattr(zipfile.ZipFile, "getinfo", _lying_getinfo)

    with pytest.raises(ValueError, match="not a valid .qualilab zip file"):
        interop.open_qualilab_project(buffer.getvalue())


def test_open_qualilab_project_rejects_zip_missing_project_json():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("something_else.json", "{}")

    with pytest.raises(ValueError, match="no project.json"):
        interop.open_qualilab_project(buffer.getvalue())


# ---------------------------------------------------------------------------
# qualilab_documents_to_records
# ---------------------------------------------------------------------------


def test_qualilab_documents_to_records_preserves_external_id():
    project = _fixture_project()

    records = interop.qualilab_documents_to_records(project, corpus_id="demo")

    assert len(records) == 9
    assert records[0].external_id == "doc-1"
    assert records[0].corpus_id == "demo"
    assert records[0].text.startswith("ENT-01")


# ---------------------------------------------------------------------------
# qualilab_doc_values_to_human_labels
# ---------------------------------------------------------------------------


def _fixture_documents() -> list[DocumentRecord]:
    project = _fixture_project()
    records = interop.qualilab_documents_to_records(project, corpus_id="demo")
    for i, record in enumerate(records, start=1):
        record.id = i  # simulate the integer PK assigned on insert
    return records


CAT_POSICAO_MAPPING = {
    "Favorável": "favoravel",
    "Cético": "cetico",
    "Ambivalente": "ambivalente",
    "Outros": "outros",
    "Não informado": "nao_informado",
}


def test_final_layer_import_accepts_full_mapping_with_full_coverage():
    project = _fixture_project()
    documents = _fixture_documents()

    result = interop.qualilab_doc_values_to_human_labels(
        project,
        category_id="cat-posicao",
        codebook_id=1,
        documents=documents,
        value_mapping=CAT_POSICAO_MAPPING,
        valid_categories=set(CAT_POSICAO_MAPPING.values()),
        layer="final",
    )

    assert result.ok, result.rejected
    assert len(result.accepted) == 9  # one "final" cat-posicao entry per document, verified in the fixture
    assert result.coverage == {"documents_with_value": 9, "total_corpus_documents": 9}
    assert {label.coder for label in result.accepted} == {"Admin"}
    assert all(label.source == "qualilab_import" for label in result.accepted)


def test_final_layer_import_rejects_all_or_nothing_on_incomplete_mapping():
    project = _fixture_project()
    documents = _fixture_documents()
    incomplete_mapping = {"Favorável": "favoravel"}  # missing the other 4 real values

    result = interop.qualilab_doc_values_to_human_labels(
        project,
        category_id="cat-posicao",
        codebook_id=1,
        documents=documents,
        value_mapping=incomplete_mapping,
        valid_categories={"favoravel"},
        layer="final",
    )

    assert not result.ok
    assert result.accepted == []  # all-or-nothing: nothing written on any rejection (finding #6)
    # 3 of the 9 real "final" cat-posicao values are "Favorável" (doc-2/5/7);
    # the other 6 (doc-1/3/4/6/8/9) have no entry in the incomplete mapping.
    assert len(result.rejected) == 6


def test_final_layer_import_rejects_mapping_to_a_nonexistent_category():
    project = _fixture_project()
    documents = _fixture_documents()
    bad_mapping = {v: "not_a_real_codebook_category" for v in CAT_POSICAO_MAPPING}

    result = interop.qualilab_doc_values_to_human_labels(
        project,
        category_id="cat-posicao",
        codebook_id=1,
        documents=documents,
        value_mapping=bad_mapping,
        valid_categories={"favoravel", "cetico"},  # doesn't include "not_a_real_codebook_category"
        layer="final",
    )

    assert not result.ok
    assert all("not a category of this codebook" in p["reason"] for p in result.rejected)


def test_individual_layer_import_produces_multiple_rows_per_document():
    project = _fixture_project()
    documents = _fixture_documents()

    result = interop.qualilab_doc_values_to_human_labels(
        project,
        category_id="cat-posicao",
        codebook_id=1,
        documents=documents,
        value_mapping=CAT_POSICAO_MAPPING,
        valid_categories=set(CAT_POSICAO_MAPPING.values()),
        layer="individual",
    )

    assert result.ok, result.rejected
    doc1_id = next(d.id for d in documents if d.external_id == "doc-1")
    doc1_labels = [label for label in result.accepted if label.document_id == doc1_id]
    assert len(doc1_labels) >= 2  # doc-1 has 3 individual-layer coders for cat-posicao in the real fixture
    assert len({label.coder for label in doc1_labels}) >= 2  # from different coders, not deduped


def test_import_rejects_a_category_id_not_declared_in_the_project():
    project = _fixture_project()
    documents = _fixture_documents()

    with pytest.raises(ValueError, match="not found in the uploaded"):
        interop.qualilab_doc_values_to_human_labels(
            project,
            category_id="does-not-exist",
            codebook_id=1,
            documents=documents,
            value_mapping=CAT_POSICAO_MAPPING,
            valid_categories=set(CAT_POSICAO_MAPPING.values()),
            layer="final",
        )


def test_individual_layer_coverage_counts_distinct_documents_not_entries():
    # doc-1 has 3 "individual"-layer coders for cat-posicao in the real
    # fixture (see test_individual_layer_import_produces_multiple_rows_per_document)
    # -- a coverage counter that increments per entry rather than per
    # distinct document would report more "documents with a value" than
    # the corpus actually has documents.
    project = _fixture_project()
    documents = _fixture_documents()

    result = interop.qualilab_doc_values_to_human_labels(
        project,
        category_id="cat-posicao",
        codebook_id=1,
        documents=documents,
        value_mapping=CAT_POSICAO_MAPPING,
        valid_categories=set(CAT_POSICAO_MAPPING.values()),
        layer="individual",
    )

    assert result.coverage["documents_with_value"] <= result.coverage["total_corpus_documents"]
    assert result.coverage["total_corpus_documents"] == 9


def test_import_raises_when_zero_documents_have_a_value():
    # category_id is real, but the corpus's documents have no matching
    # external_id (e.g. a CSV/XLSX-imported corpus) -- every doc_values
    # entry is silently skipped, and without this guard the caller would
    # get back a false "successful" 0-row import.
    project = _fixture_project()
    documents = [
        DocumentRecord(id=1, corpus_id="demo", text="unrelated content", external_id=None)
    ]

    with pytest.raises(ValueError, match="no doc_values found"):
        interop.qualilab_doc_values_to_human_labels(
            project,
            category_id="cat-posicao",
            codebook_id=1,
            documents=documents,
            value_mapping=CAT_POSICAO_MAPPING,
            valid_categories=set(CAT_POSICAO_MAPPING.values()),
            layer="final",
        )


def test_final_layer_import_rejects_a_file_with_duplicate_final_entries():
    # Synthetic project: deliberately malformed in a way the real fixture
    # never is, to exercise finding #14's guard.
    project = {
        "documents": [{"id": "doc-1", "content": "x"}],
        "categories": [{"id": "cat-a", "kind": "single", "options": ["Yes", "No"]}],
        "doc_values": [
            {"id": "v1", "document_id": "doc-1", "category_id": "cat-a", "value": "Yes",
             "author_name": "Admin", "set_by": "u1", "layer": "final"},
            {"id": "v2", "document_id": "doc-1", "category_id": "cat-a", "value": "No",
             "author_name": "Someone Else", "set_by": "u2", "layer": "final"},
        ],
    }
    documents = [DocumentRecord(id=1, corpus_id="demo", text="x", external_id="doc-1")]

    with pytest.raises(ValueError, match="more than one 'final'"):
        interop.qualilab_doc_values_to_human_labels(
            project,
            category_id="cat-a",
            codebook_id=1,
            documents=documents,
            value_mapping={"Yes": "yes", "No": "no"},
            valid_categories={"yes", "no"},
            layer="final",
        )


# ---------------------------------------------------------------------------
# inject_extractions_into_qualilab / serialize_qualilab_project
# ---------------------------------------------------------------------------


def _synthetic_project():
    return {
        "documents": [{"id": "doc-1", "content": "hello world"}],
        "categories": [{"id": "cat-a", "kind": "single", "options": ["Sim", "Nao"]}],
        "doc_values": [],
        "codings": [
            {"id": "c1", "document_id": "doc-1", "code_id": "code-1", "span_start": 0, "span_end": 5,
             "quote": "hello", "layer": "individual", "author_name": "Someone"}
        ],
    }


def test_inject_extractions_adds_a_matching_upserted_doc_value():
    project = _synthetic_project()
    documents = [DocumentRecord(id=1, corpus_id="demo", text="hello world", external_id="doc-1")]
    extractions = [ExtractionRecord(id=1, run_id=1, document_id=1, category="yes",
                                     rationale="x", evidence_span="hello")]

    result = interop.inject_extractions_into_qualilab(
        project, extractions, documents, category_id="cat-a",
        reverse_value_mapping={"yes": "Sim"}, run_id=1, model_label="test-model",
    )

    assert result.matched_count == 1
    assert result.skipped_count == 0
    entry = result.project["doc_values"][0]
    assert entry["value"] == "Sim"
    assert entry["document_id"] == "doc-1"
    assert entry["set_by"] is None
    assert entry["author_name"] == "Decifra (test-model)"
    assert entry["id"] == "cifra-1-doc-1-cat-a"


def test_inject_extractions_rejects_a_category_with_no_reverse_mapping():
    project = _synthetic_project()
    documents = [DocumentRecord(id=1, corpus_id="demo", text="hello world", external_id="doc-1")]
    extractions = [ExtractionRecord(id=1, run_id=1, document_id=1, category="yes",
                                     rationale="x", evidence_span="hello")]

    with pytest.raises(ValueError, match="reverse_value_mapping"):
        interop.inject_extractions_into_qualilab(
            project, extractions, documents, category_id="cat-a",
            reverse_value_mapping={}, run_id=1, model_label="test-model",
        )


def test_inject_extractions_rejects_a_value_not_in_declared_options():
    project = _synthetic_project()
    documents = [DocumentRecord(id=1, corpus_id="demo", text="hello world", external_id="doc-1")]
    extractions = [ExtractionRecord(id=1, run_id=1, document_id=1, category="yes",
                                     rationale="x", evidence_span="hello")]

    with pytest.raises(ValueError, match="not a declared option"):
        interop.inject_extractions_into_qualilab(
            project, extractions, documents, category_id="cat-a",
            reverse_value_mapping={"yes": "Not A Real Option"}, run_id=1, model_label="test-model",
        )


def test_inject_extractions_skips_error_category_instead_of_failing_the_whole_export():
    # run_extraction records a per-document failure as ERROR_CATEGORY
    # instead of aborting the run -- exporting a run with one failed
    # document among many good ones must not fail the entire export just
    # because "__error__" was never a real codebook category with an
    # entry in reverse_value_mapping.
    from text_as_data.extraction import ERROR_CATEGORY

    project = _synthetic_project()
    documents = [
        DocumentRecord(id=1, corpus_id="demo", text="hello world", external_id="doc-1"),
        DocumentRecord(id=2, corpus_id="demo", text="goodbye world", external_id="doc-2"),
    ]
    extractions = [
        ExtractionRecord(id=1, run_id=1, document_id=1, category="yes", rationale="x", evidence_span="hello"),
        ExtractionRecord(id=2, run_id=1, document_id=2, category=ERROR_CATEGORY, rationale="timed out", evidence_span=""),
    ]

    result = interop.inject_extractions_into_qualilab(
        project, extractions, documents, category_id="cat-a",
        reverse_value_mapping={"yes": "Sim"}, run_id=1, model_label="test-model",
    )

    assert result.matched_count == 1
    assert result.skipped_count == 1
    assert len(result.project["doc_values"]) == 1


def test_inject_extractions_rejects_zero_matched_documents():
    project = _synthetic_project()
    # A CSV-imported document has no external_id -- exactly the scenario
    # finding #10 exists to catch (must not silently "succeed" with 0
    # matches).
    documents = [DocumentRecord(id=1, corpus_id="demo", text="hello world", external_id=None)]
    extractions = [ExtractionRecord(id=1, run_id=1, document_id=1, category="yes",
                                     rationale="x", evidence_span="hello")]

    with pytest.raises(ValueError, match="zero documents matched"):
        interop.inject_extractions_into_qualilab(
            project, extractions, documents, category_id="cat-a",
            reverse_value_mapping={"yes": "Sim"}, run_id=1, model_label="test-model",
        )


def test_inject_extractions_does_not_disturb_existing_codings_or_other_doc_values():
    project = _synthetic_project()
    project["doc_values"] = [
        {"id": "v-human", "document_id": "doc-1", "category_id": "cat-a", "value": "Nao",
         "set_by": "u1", "author_name": "Human Coder", "layer": "final"}
    ]
    documents = [DocumentRecord(id=1, corpus_id="demo", text="hello world", external_id="doc-1")]
    extractions = [ExtractionRecord(id=1, run_id=1, document_id=1, category="yes",
                                     rationale="x", evidence_span="hello")]

    result = interop.inject_extractions_into_qualilab(
        project, extractions, documents, category_id="cat-a",
        reverse_value_mapping={"yes": "Sim"}, run_id=1, model_label="test-model",
    )

    assert len(result.project["doc_values"]) == 2  # the human one preserved, plus the new Decifra one
    assert result.project["codings"] == project["codings"]  # untouched
    coding = result.project["codings"][0]
    content = result.project["documents"][0]["content"]
    assert coding["quote"] == content[coding["span_start"]:coding["span_end"]]  # invariant preserved


def test_reexport_of_the_same_run_upserts_instead_of_duplicating():
    """finding #13: idempotency must be tested as a real chain (export,
    re-upload the output, export again), not by uploading the same
    original bytes twice -- the latter would pass even with a bare
    .append()."""
    project = _synthetic_project()
    documents = [DocumentRecord(id=1, corpus_id="demo", text="hello world", external_id="doc-1")]
    extractions = [ExtractionRecord(id=1, run_id=1, document_id=1, category="yes",
                                     rationale="x", evidence_span="hello")]
    original_bytes = json.dumps(project).encode("utf-8")

    first = interop.inject_extractions_into_qualilab(
        project, extractions, documents, category_id="cat-a",
        reverse_value_mapping={"yes": "Sim"}, run_id=1, model_label="test-model",
    )
    exported_bytes = interop.serialize_qualilab_project(original_bytes, first.project)

    # Re-upload the *output* of the first export as the input to the second
    # -- a genuine chain, not a repeat of the original fixture.
    reopened_project = interop.open_qualilab_project(exported_bytes)
    second = interop.inject_extractions_into_qualilab(
        reopened_project, extractions, documents, category_id="cat-a",
        reverse_value_mapping={"yes": "Sim"}, run_id=1, model_label="test-model",
    )

    matching = [e for e in second.project["doc_values"] if e["id"] == "cifra-1-doc-1-cat-a"]
    assert len(matching) == 1


def test_serialize_qualilab_project_plain_json_round_trip():
    original = b'{"documents": []}'
    project = {"documents": [], "doc_values": [{"id": "v1"}]}

    output = interop.serialize_qualilab_project(original, project)

    assert json.loads(output) == project
    assert output[:2] != b"PK"


def test_serialize_qualilab_project_zip_preserves_other_entries():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("project.json", json.dumps({"documents": []}))
        zf.writestr("pdfs/doc-1.pdf", b"%PDF-fake-binary-content")
    original = buffer.getvalue()

    updated_project = {"documents": [], "doc_values": [{"id": "new"}]}
    output = interop.serialize_qualilab_project(original, updated_project)

    with zipfile.ZipFile(io.BytesIO(output)) as zf:
        assert json.loads(zf.read("project.json")) == updated_project
        assert zf.read("pdfs/doc-1.pdf") == b"%PDF-fake-binary-content"  # carried through untouched
