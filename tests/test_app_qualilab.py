"""Endpoint-level tests for the QualiLab interop API (import corpus, import
gold labels, export). Module-level behavior is covered by
test_qualilab_interop.py; these focus on wiring: request/response shape,
status codes, and that the endpoints actually persist/read the right rows."""

from __future__ import annotations

import io
import json
from pathlib import Path

from fastapi.testclient import TestClient

from text_as_data.app import app, get_engine_dependency, get_provider_dependency
from text_as_data.db import get_engine
from text_as_data.providers import Provider, ProviderResult

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "QualiLab_synthetic_realistic_legal_ai_3.qualilab"
FIXTURE_BYTES = FIXTURE_PATH.read_bytes()

VALID_SPEC = {
    "concept": "posicao",
    "description": "Attitude towards generative AI in legal practice.",
    "categories": [
        {"label": "favoravel", "definition": "Favorable."},
        {"label": "cetico", "definition": "Skeptical."},
        {"label": "ambivalente", "definition": "Ambivalent."},
        {"label": "outros", "definition": "Other."},
        {"label": "nao_informado", "definition": "Not stated."},
    ],
}

VALUE_MAPPING = {
    "Favorável": "favoravel",
    "Cético": "cetico",
    "Ambivalente": "ambivalente",
    "Outros": "outros",
    "Não informado": "nao_informado",
}


class FakeProvider(Provider):
    def extract(self, messages, schema):
        parsed = schema(category="favoravel", rationale="because", evidence_span="quote")
        return ProviderResult(parsed=parsed, prompt="fake prompt", raw_response="fake raw response")


def _client():
    engine = get_engine("sqlite://")
    app.dependency_overrides[get_engine_dependency] = lambda: engine
    app.dependency_overrides[get_provider_dependency] = lambda: FakeProvider()
    return TestClient(app)


def _fixture_file():
    return {"file": ("project.qualilab", io.BytesIO(FIXTURE_BYTES), "application/octet-stream")}


def test_import_qualilab_creates_corpus_with_external_ids():
    client = _client()

    response = client.post("/corpora/import-qualilab", data={"name": "qlab_demo"}, files=_fixture_file())

    assert response.status_code == 200
    body = response.json()
    assert body["corpus_id"] == "qlab_demo"
    assert body["document_count"] == 9
    assert body["documents"][0]["external_id"] == "doc-1"


def test_import_qualilab_409_on_duplicate_corpus_name():
    client = _client()
    client.post("/corpora/import-qualilab", data={"name": "qlab_demo"}, files=_fixture_file())

    response = client.post("/corpora/import-qualilab", data={"name": "qlab_demo"}, files=_fixture_file())

    assert response.status_code == 409


def test_import_qualilab_labels_creates_human_labels_with_full_coverage():
    client = _client()
    client.post("/corpora/import-qualilab", data={"name": "qlab_demo"}, files=_fixture_file())
    codebook_id = client.post("/codebooks", json=VALID_SPEC).json()["id"]

    response = client.post(
        "/corpora/qlab_demo/import-qualilab-labels",
        data={
            "codebook_id": codebook_id,
            "category_id": "cat-posicao",
            "layer": "final",
            "value_mapping": json.dumps(VALUE_MAPPING),
        },
        files=_fixture_file(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["created_count"] == 9
    assert body["coverage"] == {"documents_with_value": 9, "total_corpus_documents": 9}


def test_import_qualilab_labels_400_on_non_object_value_mapping():
    # json.loads("[1,2,3]") succeeds without raising -- the endpoint must
    # not blindly call .get() on whatever JSON parses to.
    client = _client()
    client.post("/corpora/import-qualilab", data={"name": "qlab_demo"}, files=_fixture_file())
    codebook_id = client.post("/codebooks", json=VALID_SPEC).json()["id"]

    response = client.post(
        "/corpora/qlab_demo/import-qualilab-labels",
        data={
            "codebook_id": codebook_id,
            "category_id": "cat-posicao",
            "layer": "final",
            "value_mapping": json.dumps([1, 2, 3]),
        },
        files=_fixture_file(),
    )

    assert response.status_code == 400


def test_import_qualilab_labels_reimport_replaces_instead_of_duplicating():
    from sqlmodel import Session, select

    from text_as_data.app import get_engine_dependency as _get_engine_dep
    from text_as_data.db import HumanLabelRecord

    client = _client()
    engine = app.dependency_overrides[_get_engine_dep]()
    client.post("/corpora/import-qualilab", data={"name": "qlab_demo"}, files=_fixture_file())
    codebook_id = client.post("/codebooks", json=VALID_SPEC).json()["id"]
    request_kwargs = dict(
        data={
            "codebook_id": codebook_id,
            "category_id": "cat-posicao",
            "layer": "final",
            "value_mapping": json.dumps(VALUE_MAPPING),
        },
        files=_fixture_file(),
    )

    client.post("/corpora/qlab_demo/import-qualilab-labels", **request_kwargs)
    second = client.post("/corpora/qlab_demo/import-qualilab-labels", **request_kwargs)

    assert second.status_code == 200
    assert second.json()["created_count"] == 9
    with Session(engine) as session:
        rows = session.exec(
            select(HumanLabelRecord).where(HumanLabelRecord.codebook_id == codebook_id)
        ).all()
        # Re-running the same import must replace, not append -- otherwise
        # agreement_report()'s one-gold-row-per-document precondition
        # breaks the moment a researcher re-imports after fixing a
        # mismapped value.
        assert len(rows) == 9


def test_import_qualilab_labels_422_on_incomplete_mapping():
    client = _client()
    client.post("/corpora/import-qualilab", data={"name": "qlab_demo"}, files=_fixture_file())
    codebook_id = client.post("/codebooks", json=VALID_SPEC).json()["id"]

    response = client.post(
        "/corpora/qlab_demo/import-qualilab-labels",
        data={
            "codebook_id": codebook_id,
            "category_id": "cat-posicao",
            "layer": "final",
            "value_mapping": json.dumps({"Favorável": "favoravel"}),  # incomplete on purpose
        },
        files=_fixture_file(),
    )

    assert response.status_code == 422
    # 3 of the 9 real "final" cat-posicao values are "Favorável"; the other
    # 6 have no entry in this deliberately incomplete mapping.
    assert len(response.json()["detail"]["problems"]) == 6


def test_export_run_to_qualilab_returns_updated_file_with_count_headers():
    client = _client()
    client.post("/corpora/import-qualilab", data={"name": "qlab_demo"}, files=_fixture_file())
    codebook_id = client.post("/codebooks", json=VALID_SPEC).json()["id"]
    run_id = client.post(
        "/runs", json={"codebook_id": codebook_id, "corpus_id": "qlab_demo", "model": "fake-model"}
    ).json()["run_id"]

    reverse_mapping = {v: k for k, v in VALUE_MAPPING.items()}
    response = client.post(
        f"/runs/{run_id}/export-qualilab",
        data={"category_id": "cat-posicao", "reverse_value_mapping": json.dumps(reverse_mapping)},
        files=_fixture_file(),
    )

    assert response.status_code == 200
    assert response.headers["X-Decifra-Matched-Count"] == "9"
    assert response.headers["X-Decifra-Skipped-Count"] == "0"

    exported = json.loads(response.content)
    cifra_entries = [v for v in exported["doc_values"] if v["author_name"].startswith("Decifra")]
    assert len(cifra_entries) == 9
    assert all(v["value"] == "Favorável" for v in cifra_entries)  # FakeProvider always answers "favoravel"


def test_export_run_to_qualilab_422_on_corpus_with_no_external_ids():
    client = _client()
    client.post("/corpora/paste", json={"name": "plain_corpus", "text": "no qualilab id here"})
    codebook_id = client.post("/codebooks", json=VALID_SPEC).json()["id"]
    run_id = client.post(
        "/runs", json={"codebook_id": codebook_id, "corpus_id": "plain_corpus", "model": "fake-model"}
    ).json()["run_id"]

    response = client.post(
        f"/runs/{run_id}/export-qualilab",
        data={"category_id": "cat-posicao", "reverse_value_mapping": json.dumps({"favoravel": "Favorável"})},
        files=_fixture_file(),
    )

    assert response.status_code == 422
