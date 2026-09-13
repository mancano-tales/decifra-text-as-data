from fastapi.testclient import TestClient
from sqlmodel import Session

from text_as_data.app import app, get_engine_dependency, get_provider_dependency
from text_as_data.db import CodebookRecord, DocumentRecord, get_engine
from text_as_data.providers import Provider, ProviderResult

YAML_SOURCE = """
concept: test_concept
description: "A test codebook."
categories:
  - label: yes
    definition: "Positive case."
  - label: no
    definition: "Negative case."
"""


class FakeProvider(Provider):
    def extract(self, messages, schema):
        parsed = schema(category="yes", rationale="because", evidence_span="quote")
        return ProviderResult(parsed=parsed, prompt="fake prompt", raw_response="fake raw response")


def _make_test_client():
    engine = get_engine("sqlite://")
    with Session(engine) as session:
        codebook = CodebookRecord(name="test", yaml_raw=YAML_SOURCE)
        session.add(codebook)
        session.add(DocumentRecord(corpus_id="test_corpus", text="doc 1"))
        session.commit()
        session.refresh(codebook)
        codebook_id = codebook.id

    app.dependency_overrides[get_engine_dependency] = lambda: engine
    app.dependency_overrides[get_provider_dependency] = lambda: FakeProvider()
    return TestClient(app), codebook_id


def test_post_runs_then_get_results():
    client, codebook_id = _make_test_client()

    response = client.post(
        "/runs", json={"codebook_id": codebook_id, "corpus_id": "test_corpus", "model": "fake-model"}
    )
    assert response.status_code == 200
    run_id = response.json()["run_id"]

    status = client.get(f"/runs/{run_id}").json()
    assert status["status"] == "done"
    assert status["processed"] == 1
    assert status["total"] == 1

    results = client.get(f"/runs/{run_id}/results").json()
    assert len(results) == 1
    assert results[0]["category"] == "yes"


def test_post_runs_with_unknown_codebook_returns_404():
    client, _ = _make_test_client()

    response = client.post("/runs", json={"codebook_id": 999, "corpus_id": "test_corpus", "model": "fake-model"})

    assert response.status_code == 404


def test_get_results_for_unknown_run_returns_404():
    client, _ = _make_test_client()

    response = client.get("/runs/999/results")

    assert response.status_code == 404


def test_post_runs_with_unknown_corpus_returns_404():
    client, codebook_id = _make_test_client()

    response = client.post(
        "/runs", json={"codebook_id": codebook_id, "corpus_id": "no_such_corpus", "model": "fake-model"}
    )

    assert response.status_code == 404
    assert "no_such_corpus" in response.json()["detail"]


def test_extractions_with_snippets_chunks_the_in_clause(monkeypatch):
    # SQLite's default build caps a single statement at 999 bound
    # parameters -- a run with more distinct documents than that would
    # otherwise raise "too many SQL variables" on the single un-chunked
    # `IN (...)` query. Monkeypatching the chunk size down to 2 lets this
    # test exercise the chunking loop without seeding hundreds of documents.
    import text_as_data.app as app_module
    from text_as_data.db import ExtractionRecord

    monkeypatch.setattr(app_module, "_SQLITE_MAX_IN_CLAUSE", 2)
    engine = get_engine("sqlite://")
    with Session(engine) as session:
        docs = [DocumentRecord(corpus_id="c", text=f"doc {i}") for i in range(5)]
        for d in docs:
            session.add(d)
        session.commit()
        for d in docs:
            session.refresh(d)
        extractions = [
            ExtractionRecord(run_id=1, document_id=d.id, category="yes", rationale="", evidence_span="")
            for d in docs
        ]

        rows = app_module._extractions_with_snippets(session, extractions)

        assert len(rows) == 5
        assert all(row["document_snippet"] for row in rows)


def test_get_provider_dependency_builds_provider_for_the_requested_model(monkeypatch):
    from text_as_data.app import CreateRunRequest, get_provider_dependency

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-a-real-secret")
    request = CreateRunRequest(codebook_id=1, corpus_id="c", model="claude-haiku-4-5")

    provider = get_provider_dependency(request)

    assert provider._model == "claude-haiku-4-5"


def test_get_provider_dependency_builds_openai_provider_for_gpt_model(monkeypatch):
    from text_as_data.app import CreateRunRequest, get_provider_dependency

    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-a-real-secret")
    request = CreateRunRequest(codebook_id=1, corpus_id="c", model="gpt-4o")

    provider = get_provider_dependency(request)

    assert provider._model == "gpt-4o"


def test_get_provider_dependency_rejects_a_model_with_no_known_vendor_prefix():
    from fastapi import HTTPException

    from text_as_data.app import CreateRunRequest, get_provider_dependency

    # Previously this silently fell through to a hardcoded `vendor="anthropic"`,
    # so a non-Anthropic model name would be sent to the Anthropic API instead
    # of failing loudly.
    request = CreateRunRequest(codebook_id=1, corpus_id="c", model="mystery-model-9000")

    try:
        get_provider_dependency(request)
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 422
        assert "mystery-model-9000" in exc.detail


def test_get_provider_dependency_builds_cli_provider_when_requested():
    from text_as_data.app import CreateRunRequest, get_provider_dependency
    from text_as_data.providers import CliProvider

    request = CreateRunRequest(
        codebook_id=1,
        corpus_id="c",
        model="gemini-agy",
        provider_mode="cli",
        cli_command=["agy", "-p"],
        cli_prompt_mode="arg",
    )

    provider = get_provider_dependency(request)

    assert isinstance(provider, CliProvider)
    assert provider._prompt_mode == "arg"


def test_get_provider_dependency_requires_cli_command_for_cli_mode():
    from fastapi import HTTPException

    from text_as_data.app import CreateRunRequest, get_provider_dependency

    request = CreateRunRequest(codebook_id=1, corpus_id="c", model="x", provider_mode="cli")

    try:
        get_provider_dependency(request)
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 422
