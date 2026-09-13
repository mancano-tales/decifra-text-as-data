import io

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
    client.post("/corpora/paste", json={"name": "demo", "text": "About 200 people occupied the square."})
    run_id = client.post(
        "/runs", json={"codebook_id": codebook_id, "corpus_id": "demo", "model": "fake-model"}
    ).json()["run_id"]

    return client, codebook_id, run_id


def test_get_run_results_includes_document_snippet():
    client, codebook_id, run_id = _make_test_client()

    response = client.get(f"/runs/{run_id}/results")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["document_snippet"].startswith("About 200 people occupied")
    assert body[0]["category"] == "protest"


def test_list_runs_returns_run_with_codebook_name_and_counts():
    client, codebook_id, run_id = _make_test_client()

    response = client.get("/runs")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == run_id
    assert body[0]["corpus_id"] == "demo"
    assert body[0]["codebook_id"] == codebook_id
    assert body[0]["codebook_name"] == "protest"
    assert body[0]["status"] == "done"
    assert body[0]["processed"] == 1
    assert body[0]["total"] == 1


def test_update_extraction_changes_category_and_rationale():
    client, codebook_id, run_id = _make_test_client()
    extraction_id = client.get(f"/runs/{run_id}/results").json()[0]["id"]

    response = client.put(
        f"/runs/{run_id}/results/{extraction_id}",
        json={"category": "not_protest", "rationale": "corrected by hand"},
    )

    assert response.status_code == 200
    assert response.json()["category"] == "not_protest"
    body = client.get(f"/runs/{run_id}/results").json()
    assert body[0]["category"] == "not_protest"
    assert body[0]["rationale"] == "corrected by hand"


def test_update_extraction_rejects_invalid_category():
    client, codebook_id, run_id = _make_test_client()
    extraction_id = client.get(f"/runs/{run_id}/results").json()[0]["id"]

    response = client.put(
        f"/runs/{run_id}/results/{extraction_id}",
        json={"category": "not_a_real_label", "rationale": "x"},
    )

    assert response.status_code == 422


def test_update_extraction_404_for_unknown_extraction():
    client, codebook_id, run_id = _make_test_client()

    response = client.put(
        f"/runs/{run_id}/results/999",
        json={"category": "protest", "rationale": "x"},
    )

    assert response.status_code == 404


def test_export_run_results_csv():
    client, codebook_id, run_id = _make_test_client()

    response = client.get(f"/runs/{run_id}/export?format=csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "protest" in response.text


def test_export_run_results_json():
    client, codebook_id, run_id = _make_test_client()

    response = client.get(f"/runs/{run_id}/export?format=json")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["category"] == "protest"


def test_export_run_results_xlsx():
    import openpyxl

    client, codebook_id, run_id = _make_test_client()

    response = client.get(f"/runs/{run_id}/export?format=xlsx")

    assert response.status_code == 200
    workbook = openpyxl.load_workbook(io.BytesIO(response.content))
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    assert len(rows) == 2  # header + 1 data row


def test_export_run_results_404_for_unknown_run():
    client, codebook_id, run_id = _make_test_client()

    response = client.get("/runs/999/export?format=csv")

    assert response.status_code == 404


def test_run_persists_provider_mode_and_detail_for_disclosure():
    client, codebook_id, run_id = _make_test_client()

    response = client.get(f"/runs/{run_id}/disclosure")

    assert response.status_code == 200
    body = response.json()
    b1 = body["B_model_and_access_details"]["B1_model_name_provider_version_date"]
    assert b1["provider_mode"] == "api_key"  # _make_test_client's default CreateRunRequest
    assert b1["model"] == "fake-model"


def test_get_run_disclosure_404_for_unknown_run():
    client, codebook_id, run_id = _make_test_client()

    response = client.get("/runs/999/disclosure")

    assert response.status_code == 404


def test_get_run_disclosure_reports_prompt_audit_trail_coverage():
    client, codebook_id, run_id = _make_test_client()

    response = client.get(f"/runs/{run_id}/disclosure")

    assert response.status_code == 200
    c1 = response.json()["C_prompting"]["C1_exact_prompts"]
    assert "1 of 1 documents" in c1
