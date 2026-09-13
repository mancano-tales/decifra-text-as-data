from fastapi.testclient import TestClient

from text_as_data.app import app, get_engine_dependency, get_provider_dependency
from text_as_data.db import get_engine
from text_as_data.providers import Provider, ProviderResult

VALID_SPEC = {
    "concept": "protest",
    "description": "A collective public event.",
    "categories": [
        {"label": "protest", "definition": "An occupation, march, or strike."},
        {"label": "not_protest", "definition": "Any event that does not meet the criteria above."},
    ],
}


class FakeProvider(Provider):
    def extract(self, messages, schema):
        parsed = schema(category="protest", rationale="because", evidence_span="quote")
        return ProviderResult(parsed=parsed, prompt="fake prompt", raw_response="fake raw response")


def _make_test_client():
    engine = get_engine("sqlite://")
    app.dependency_overrides[get_engine_dependency] = lambda: engine
    app.dependency_overrides[get_provider_dependency] = lambda: FakeProvider()
    client = TestClient(app)

    codebook_id = client.post("/codebooks", json=VALID_SPEC).json()["id"]
    client.post("/corpora/paste", json={"name": "demo", "text": "document 0"})
    run_id = client.post(
        "/runs", json={"codebook_id": codebook_id, "corpus_id": "demo", "model": "fake-model"}
    ).json()["run_id"]

    return client, codebook_id, run_id


def _document_id(client, run_id: int) -> int:
    return client.get(f"/runs/{run_id}/results").json()[0]["document_id"]


def test_upload_gold_labels_creates_human_label_rows():
    client, codebook_id, run_id = _make_test_client()
    document_id = _document_id(client, run_id)
    csv_content = f"document_id,gold_category\n{document_id},not_protest\n".encode("utf-8")

    response = client.post(
        f"/runs/{run_id}/gold-labels",
        files={"file": ("gold.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    assert response.json() == {"imported": 1, "skipped_blank": 0}


def test_upload_gold_labels_skips_blank_rows_without_error():
    client, codebook_id, run_id = _make_test_client()
    document_id = _document_id(client, run_id)
    csv_content = f"document_id,gold_category\n{document_id},\n".encode("utf-8")

    response = client.post(
        f"/runs/{run_id}/gold-labels",
        files={"file": ("gold.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    assert response.json() == {"imported": 0, "skipped_blank": 1}


def test_upload_gold_labels_rejects_whole_file_on_invalid_category():
    client, codebook_id, run_id = _make_test_client()
    document_id = _document_id(client, run_id)
    csv_content = f"document_id,gold_category\n{document_id},not_a_real_label\n".encode("utf-8")

    response = client.post(
        f"/runs/{run_id}/gold-labels",
        files={"file": ("gold.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 422
    assert "not_a_real_label" in response.json()["detail"]


def test_upload_gold_labels_404_for_unknown_run():
    client, codebook_id, run_id = _make_test_client()
    csv_content = b"document_id,gold_category\n1,protest\n"

    response = client.post(
        "/runs/999/gold-labels",
        files={"file": ("gold.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 404


def test_upload_gold_labels_422_on_missing_required_columns():
    client, codebook_id, run_id = _make_test_client()
    csv_content = b"id,category\n1,protest\n"

    response = client.post(
        f"/runs/{run_id}/gold-labels",
        files={"file": ("gold.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 422


def test_upload_gold_labels_422_on_non_integer_document_id():
    client, codebook_id, run_id = _make_test_client()
    csv_content = b"document_id,gold_category\nnot-a-number,protest\n"

    response = client.post(
        f"/runs/{run_id}/gold-labels",
        files={"file": ("gold.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 422


def test_upload_gold_labels_reimport_replaces_the_manual_correction_instead_of_adding_a_coder():
    client, codebook_id, run_id = _make_test_client()
    document_id = _document_id(client, run_id)
    csv_content = f"document_id,gold_category\n{document_id},not_protest\n".encode("utf-8")
    client.post(f"/runs/{run_id}/gold-labels", files={"file": ("gold.csv", csv_content, "text/csv")})

    # Re-upload correcting the same document's value.
    corrected = f"document_id,gold_category\n{document_id},protest\n".encode("utf-8")
    response = client.post(f"/runs/{run_id}/gold-labels", files={"file": ("gold.csv", corrected, "text/csv")})

    assert response.status_code == 200
    report = client.get(f"/runs/{run_id}/validation").json()
    # If the re-upload had appended instead of replaced, this document
    # would show up as excluded_multi_coder instead of labeled.
    assert report["coverage"] == {"labeled": 1, "total": 1, "excluded_multi_coder": 0}


def _upload_gold(client, run_id, document_id, category):
    csv_content = f"document_id,gold_category\n{document_id},{category}\n".encode("utf-8")
    response = client.post(
        f"/runs/{run_id}/gold-labels", files={"file": ("gold.csv", csv_content, "text/csv")}
    )
    assert response.status_code == 200
    return response


def test_validation_report_returns_coverage_and_metrics():
    client, codebook_id, run_id = _make_test_client()
    document_id = _document_id(client, run_id)
    _upload_gold(client, run_id, document_id, "protest")  # matches FakeProvider's prediction

    response = client.get(f"/runs/{run_id}/validation")

    assert response.status_code == 200
    body = response.json()
    assert body["coverage"] == {"labeled": 1, "total": 1, "excluded_multi_coder": 0}
    assert body["per_category"]["accuracy"] == 1.0
    assert body["disagreements"] == []


def test_validation_report_lists_disagreements_with_snippet():
    client, codebook_id, run_id = _make_test_client()
    document_id = _document_id(client, run_id)
    _upload_gold(client, run_id, document_id, "not_protest")  # FakeProvider predicts "protest"

    response = client.get(f"/runs/{run_id}/validation")

    assert response.status_code == 200
    body = response.json()
    assert body["per_category"]["accuracy"] == 0.0
    assert len(body["disagreements"]) == 1
    disagreement = body["disagreements"][0]
    assert disagreement["predicted"] == "protest"
    assert disagreement["gold"] == "not_protest"
    assert "document_snippet" in disagreement


def test_validation_report_excludes_multi_coder_documents():
    from sqlmodel import Session

    from text_as_data.app import get_engine_dependency as _get_engine_dep
    from text_as_data.db import HumanLabelRecord

    client, codebook_id, run_id = _make_test_client()
    document_id = _document_id(client, run_id)
    _upload_gold(client, run_id, document_id, "protest")
    # A second, differently-sourced gold entry for the SAME document
    # simulates a QualiLab multi-coder import -- the report must exclude
    # this document rather than pick one value silently. (Written directly
    # rather than via a second /gold-labels upload, since that endpoint's
    # own replace-on-reimport semantics would just replace the manual
    # row instead of adding a second one -- this needs a genuinely
    # different coder/source, the way a real multi-coder import would.)
    engine = app.dependency_overrides[_get_engine_dep]()
    with Session(engine) as session:
        session.add(
            HumanLabelRecord(
                document_id=document_id,
                codebook_id=codebook_id,
                category="not_protest",
                coder="second_coder",
                source="qualilab_import",
                layer="individual",
            )
        )
        session.commit()

    response = client.get(f"/runs/{run_id}/validation")

    assert response.status_code == 200
    body = response.json()
    assert body["coverage"] == {"labeled": 0, "total": 1, "excluded_multi_coder": 1}
    assert body["disagreements"] == []


def test_validation_report_404_for_unknown_run():
    client, codebook_id, run_id = _make_test_client()

    response = client.get("/runs/999/validation")

    assert response.status_code == 404


def test_validation_report_empty_before_any_gold_labels():
    client, codebook_id, run_id = _make_test_client()

    response = client.get(f"/runs/{run_id}/validation")

    assert response.status_code == 200
    body = response.json()
    assert body["coverage"] == {"labeled": 0, "total": 1, "excluded_multi_coder": 0}
    assert body["per_category"] == {}
    assert body["disagreements"] == []
