import hashlib
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from text_as_data import app as api, config
from text_as_data.codebook import Codebook
from text_as_data.db import CodebookRecord, DocumentRecord, ExtractionRecord, RunRecord, get_engine
from text_as_data.providers import ProviderResult, ApiKeyProvider
from text_as_data.webapp import mount_frontend

YAML = """concept: test
description: Classify the text.
categories:
  - label: yes
    definition: A positive case.
  - label: no
    definition: Other cases.
"""


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECIFRA_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(config.keyring, "get_password", lambda *args: None)
    engine = get_engine("sqlite://")
    saved = dict(api.app.dependency_overrides)
    api.app.dependency_overrides.clear()
    api.app.dependency_overrides[api.get_engine_dependency] = lambda: engine
    with Session(engine) as session:
        session.add(CodebookRecord(name="test", yaml_raw=YAML))
        session.add(DocumentRecord(corpus_id="sample", text="A positive case of collective action."))
        session.commit()
    yield TestClient(api.app), engine
    api.app.dependency_overrides.clear()
    api.app.dependency_overrides.update(saved)
    engine.dispose()


def request(**kwargs):
    return {"codebook_id":1,"corpus_id":"sample","model":"test-cli","provider_mode":"cli", **kwargs}


def test_estimate_cache_bypass_and_review_exclusion(client):
    http, engine = client
    before = http.post("/runs/estimate", json=request()).json()
    assert before["new_documents"] == 1 and before["input_tokens"] > 10
    assert before["estimated_usd"] is None
    with Session(engine) as session:
        variable = Codebook.from_yaml_string(YAML).variables[0]
        run = RunRecord(codebook_id=1, corpus_id="sample", model="test-cli", provider_mode="cli", codebook_yaml_hash=hashlib.sha256(YAML.encode()).hexdigest())
        session.add(run); session.commit(); session.refresh(run)
        session.add(ExtractionRecord(run_id=run.id, document_id=1, variable=variable.name, variable_spec_hash=variable.spec_hash, category="yes",rationale="original",evidence_span="collective action")); session.commit()
        run_id = run.id
    assert http.post("/runs/estimate",json=request()).json()["cached_documents"] == 1
    assert http.post("/runs/estimate",json=request(bypass_cache=True)).json()["new_documents"] == 1
    assert http.post("/runs/estimate",json=request(provider_mode="api_key")).json()["new_documents"] == 1
    for reason in ["first review", "second review"]:
        result = http.put(f"/runs/{run_id}/results/1",json={"category":"no","rationale":reason})
        assert result.status_code == 200
        assert json.loads(result.json()["original_result_json"])["rationale"] == "original"
    assert http.post("/runs/estimate",json=request()).json()["new_documents"] == 1
    calls = []
    def extract(messages, schema):
        calls.append(messages)
        return ProviderResult(parsed=schema(category="yes",rationale="new model answer",evidence_span="collective action"),prompt="test",raw_response="test")
    api.app.dependency_overrides[api.get_provider_dependency] = lambda: SimpleNamespace(extract=extract)
    fresh = http.post("/runs",json=request()).json()["run_id"]
    assert len(calls) == 1
    assert http.get(f"/runs/{fresh}/results").json()[0]["rationale"] == "new model answer"


def test_settings_persist_without_returning_or_serializing_key(client, monkeypatch):
    http, _ = client
    vault = {}
    monkeypatch.setattr(api, "save_api_key", lambda vendor, value: vault.update({vendor:value}))
    monkeypatch.setattr(config.keyring, "get_password", lambda service, vendor: vault.get(vendor))
    response = http.put("/settings",json={"model":"gpt-test","openai_api_key":"synthetic-secret","input_usd_per_million":2,"output_usd_per_million":8})
    assert response.status_code == 200
    assert "synthetic-secret" not in response.text
    assert "synthetic-secret" not in config.config_path().read_text()
    assert http.get("/settings").json()["credentials"]["openai"]["configured"]
    assert config.read_settings().model == "gpt-test"
    estimate = http.post("/runs/estimate",json=request(provider_mode="api_key")).json()
    assert estimate["estimated_usd"] > 0
    monkeypatch.setenv("OPENAI_API_KEY", "environment-value")
    assert config.api_key("openai") == "environment-value"
    assert http.get("/settings").json()["credentials"]["openai"]["source"] == "environment"


def test_settings_reject_insecure_storage_and_invalid_rates(client, monkeypatch):
    http, _ = client
    monkeypatch.setattr(config.keyring, "get_keyring", lambda: object())
    response = http.put("/settings",json={"anthropic_api_key":"synthetic-secret"})
    assert response.status_code == 503 and "synthetic-secret" not in response.text
    assert not config.config_path().exists()
    assert http.put("/settings",json={"input_usd_per_million":-1}).status_code == 422


def test_missing_api_key_fails_before_creating_run(client):
    http, _ = client
    assert http.post("/runs",json=request(provider_mode="api_key",model="gpt-test")).status_code == 422
    assert http.get("/runs").json() == []


def test_single_origin_serves_frontend_and_keeps_api_routes(tmp_path):
    (tmp_path / "index.html").write_text("<h1>Decifra</h1>")
    (tmp_path / "bundle.js").write_text("console.log('ready')")
    app = FastAPI()
    @app.get("/settings")
    def settings(): return {"ready":True}
    mount_frontend(app,tmp_path)
    http = TestClient(app)
    assert "Decifra" in http.get("/").text
    assert http.get("/bundle.js").status_code == 200
    assert http.get("/settings").json() == {"ready":True}
    assert http.get("/missing.js").status_code == 404


def test_provider_records_usage_when_sdk_exposes_it():
    from pydantic import BaseModel
    class Label(BaseModel):
        category: str
    result = Label(category="yes")
    object.__setattr__(result,"_raw_response",SimpleNamespace(usage=SimpleNamespace(input_tokens=80,output_tokens=20)))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs:result)))
    assert ApiKeyProvider(client,"model").extract([],Label).tokens_used == 100


def test_estimate_missing_corpus_or_codebook(client):
    http, _ = client
    assert http.post("/runs/estimate",json=request(corpus_id="missing")).status_code == 404
    assert http.post("/runs/estimate",json=request(codebook_id=999)).status_code == 404


def test_multi_variable_codebook_runs_from_api_through_estimate_and_sqlite(client):
    http, engine = client
    codebook_spec = {
        "concept": "multi test",
        "description": "A synthetic API integration codebook.",
        "variables": [
            {
                "name": "event_type",
                "description": "What kind of event is described?",
                "categories": [
                    {"label": "protest", "definition": "A public protest."},
                    {"label": "other", "definition": "Something else."},
                ],
            },
            {
                "name": "areas",
                "description": "Which areas of concern apply?",
                "multi_label": True,
                "max_labels": 2,
                "categories": [
                    {"label": "land", "definition": "Land conflict is central."},
                    {"label": "rights", "definition": "Rights are central."},
                ],
            },
        ],
    }
    created = http.post("/codebooks", json=codebook_spec)
    assert created.status_code == 200, created.text
    codebook_id = created.json()["id"]
    run_request = request(codebook_id=codebook_id)

    estimate = http.post("/runs/estimate", json=run_request)
    assert estimate.status_code == 200, estimate.text
    assert estimate.json()["total_calls"] == 2
    assert estimate.json()["new_calls"] == 2
    assert estimate.json()["output_tokens"] == config.read_settings().output_tokens_per_document * 3

    calls = []

    def extract(messages, schema):
        calls.append(messages)
        properties = schema.model_json_schema()["properties"]
        quote = messages[-1]["content"]
        if "category" in properties:
            parsed = schema(category=properties["category"]["enum"][0], rationale="single", evidence_span=quote)
        else:
            selection_type = schema.model_fields["selections"].annotation.__args__[0]
            label = selection_type.model_json_schema()["properties"]["label"]["enum"][0]
            parsed = schema(
                selections=[selection_type(label=label, rationale="per label", evidence_span=quote)],
                rationale="set rationale",
            )
        return ProviderResult(parsed=parsed, prompt="api prompt", raw_response=parsed.model_dump_json())

    api.app.dependency_overrides[api.get_provider_dependency] = lambda: SimpleNamespace(extract=extract)
    run_id = http.post("/runs", json=run_request).json()["run_id"]
    results = http.get(f"/runs/{run_id}/results").json()
    assert len(calls) == 2
    assert {row["variable"] for row in results} == {"event_type", "areas"}
    areas = next(row for row in results if row["variable"] == "areas")
    assert areas["category"] == ""
    assert json.loads(areas["selections_json"])[0]["label"] == "land"

    cached_estimate = http.post("/runs/estimate", json=run_request).json()
    assert cached_estimate["cached_calls"] == 2
    assert cached_estimate["new_calls"] == 0
    with Session(engine) as session:
        persisted = session.exec(
            select(ExtractionRecord).where(ExtractionRecord.run_id == run_id)
        ).all()
        assert len(persisted) == 2


def test_validation_coverage_excludes_other_corpora(client):
    from text_as_data.db import HumanLabelRecord
    http, engine = client
    with Session(engine) as session:
        other = DocumentRecord(corpus_id="other",text="Other document")
        run = RunRecord(codebook_id=1,corpus_id="sample",model="test")
        session.add(other); session.add(run); session.commit(); session.refresh(other); session.refresh(run)
        session.add(HumanLabelRecord(document_id=other.id,codebook_id=1,category="yes",coder="manual")); session.commit()
        run_id=run.id
    report=http.get(f"/runs/{run_id}/validation").json()
    assert report["coverage"]["total"] == 1
    assert report["coverage"]["labeled"] == 0
