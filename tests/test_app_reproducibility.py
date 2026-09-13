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


class ConstantProvider(Provider):
    """Always answers the same way -- for the "runs agree" case."""

    def extract(self, messages, schema):
        parsed = schema(category="protest", rationale="because", evidence_span="quote")
        return ProviderResult(parsed=parsed, prompt="fake prompt", raw_response="fake raw response")


class FlakyProvider(Provider):
    """Disagrees with ConstantProvider on every other call -- simulates the
    real non-determinism a genuine reproducibility check exists to catch,
    without depending on an actual LLM's randomness in a test."""

    def __init__(self):
        self.calls = 0

    def extract(self, messages, schema):
        self.calls += 1
        category = "protest" if self.calls % 2 else "not_protest"
        parsed = schema(category=category, rationale="because", evidence_span="quote")
        return ProviderResult(parsed=parsed, prompt="fake prompt", raw_response="fake raw response")


def _make_test_client():
    engine = get_engine("sqlite://")
    app.dependency_overrides[get_engine_dependency] = lambda: engine
    client = TestClient(app)

    codebook_id = client.post("/codebooks", json=VALID_SPEC).json()["id"]
    client.post("/corpora/paste", json={"name": "demo", "text": "About 200 people occupied the square."})
    return client, codebook_id


def _run(client, codebook_id, provider, bypass_cache=False):
    app.dependency_overrides[get_provider_dependency] = lambda: provider
    return client.post(
        "/runs",
        json={"codebook_id": codebook_id, "corpus_id": "demo", "model": "fake-model", "bypass_cache": bypass_cache},
    ).json()["run_id"]


def test_bypass_cache_true_calls_the_provider_even_when_a_cached_answer_exists():
    client, codebook_id = _make_test_client()
    flaky = FlakyProvider()
    run_a = _run(client, codebook_id, flaky)  # flaky.calls == 1 -> "protest", cached now
    assert flaky.calls == 1

    run_b = _run(client, codebook_id, flaky, bypass_cache=True)

    assert flaky.calls == 2  # proves the cache was NOT served for run_b
    categoria_b = client.get(f"/runs/{run_b}/results").json()[0]["category"]
    assert categoria_b == "not_protest"  # flaky's 2nd call -- different from run_a's cached "protest"


def test_bypass_cache_false_default_serves_the_cache_and_never_calls_the_provider_again():
    client, codebook_id = _make_test_client()
    flaky = FlakyProvider()
    _run(client, codebook_id, flaky)
    assert flaky.calls == 1

    _run(client, codebook_id, flaky)  # bypass_cache defaults to False

    assert flaky.calls == 1  # cache hit -- provider never called a second time


def test_reproducibility_report_on_identical_runs_is_perfect_agreement():
    client, codebook_id = _make_test_client()
    run_a = _run(client, codebook_id, ConstantProvider())
    run_b = _run(client, codebook_id, ConstantProvider(), bypass_cache=True)

    response = client.get(f"/runs/{run_a}/reproducibility", params={"compare_to": run_b})

    assert response.status_code == 200
    body = response.json()
    assert body["run_a"] == run_a
    assert body["run_b"] == run_b
    assert body["per_column"]["category"]["exact_match_rate"] == 1.0
    assert body["mismatches"] == []


def test_reproducibility_report_on_flaky_runs_surfaces_the_disagreement():
    client, codebook_id = _make_test_client()
    flaky = FlakyProvider()
    run_a = _run(client, codebook_id, flaky)  # "protest"
    run_b = _run(client, codebook_id, flaky, bypass_cache=True)  # "not_protest"

    response = client.get(f"/runs/{run_a}/reproducibility", params={"compare_to": run_b})

    assert response.status_code == 200
    body = response.json()
    assert body["per_column"]["category"]["exact_match_rate"] == 0.0
    assert body["mismatches"][0]["run_a"] == "protest"
    assert body["mismatches"][0]["run_b"] == "not_protest"


def test_reproducibility_report_422_when_runs_use_different_codebooks():
    client, codebook_id = _make_test_client()
    other_codebook_id = client.post("/codebooks", json=VALID_SPEC).json()["id"]
    run_a = _run(client, codebook_id, ConstantProvider())
    run_b = _run(client, other_codebook_id, ConstantProvider())

    response = client.get(f"/runs/{run_a}/reproducibility", params={"compare_to": run_b})

    assert response.status_code == 422


def test_reproducibility_report_404_for_unknown_run():
    client, codebook_id = _make_test_client()
    run_a = _run(client, codebook_id, ConstantProvider())

    response = client.get(f"/runs/{run_a}/reproducibility", params={"compare_to": 999})

    assert response.status_code == 404
