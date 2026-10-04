"""Configurable CLI timeout per run and a readable timeout error (issue #11).

The bbsia-radar pilot lost 9% of its extractions to CliProvider's fixed
180-second timeout, and each failure stored the whole command line, prompt
included, as the extraction's rationale."""

import subprocess

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlmodel import Session, select

from text_as_data.app import CreateRunRequest, app, get_engine_dependency, get_provider_dependency
from text_as_data.db import ExtractionRecord, RunRecord, get_engine
from text_as_data.extraction import ERROR_CATEGORY
from text_as_data.providers import Provider

SPEC = {
    "concept": "protest",
    "description": "A collective public event.",
    "categories": [
        {"label": "protest", "definition": "An occupation, march, or strike."},
        {"label": "not_protest", "definition": "Any event that does not meet the criteria above."},
    ],
}


def test_cli_timeout_defaults_to_180_and_reaches_the_provider():
    default = CreateRunRequest(codebook_id=1, corpus_id="c", model="m", provider_mode="cli", cli_command=["agy", "-p"])
    assert default.cli_timeout_seconds == 180
    assert get_provider_dependency(default)._timeout == 180

    longer = CreateRunRequest(codebook_id=1, corpus_id="c", model="m", provider_mode="cli",
                              cli_command=["agy", "-p"], cli_timeout_seconds=600)
    assert get_provider_dependency(longer)._timeout == 600


@pytest.mark.parametrize("value", [0, 5, 3601])
def test_cli_timeout_outside_bounds_is_rejected(value):
    with pytest.raises(ValidationError):
        CreateRunRequest(codebook_id=1, corpus_id="c", model="m", cli_timeout_seconds=value)


class TimingOutProvider(Provider):
    def extract(self, messages, schema):
        prompt = "x" * 5000
        raise subprocess.TimeoutExpired(cmd=["agy", "--model", "m", "-p", prompt], timeout=42)


def test_timeout_is_recorded_on_the_run_and_stored_as_a_short_error():
    engine = get_engine("sqlite://")
    app.dependency_overrides[get_engine_dependency] = lambda: engine
    app.dependency_overrides[get_provider_dependency] = lambda: TimingOutProvider()
    try:
        client = TestClient(app)
        codebook_id = client.post("/codebooks", json=SPEC).json()["id"]
        client.post("/corpora/paste", json={"name": "c", "text": "document"})
        run_id = client.post("/runs", json={
            "codebook_id": codebook_id, "corpus_id": "c", "model": "m",
            "provider_mode": "cli", "cli_command": ["agy", "-p"], "cli_timeout_seconds": 42,
        }).json()["run_id"]
    finally:
        app.dependency_overrides.clear()

    with Session(engine) as session:
        assert session.get(RunRecord, run_id).cli_timeout_seconds == 42
        row = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == run_id)).one()
    assert row.category == ERROR_CATEGORY
    assert row.rationale == "CLI timed out after 42 seconds"
    assert "xxxx" not in row.rationale
