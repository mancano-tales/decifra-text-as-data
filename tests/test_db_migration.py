"""Regression tests for the additive column migration in db.py's
get_engine() -- the mechanism that fixes the recurring "existing shared
decifra.sqlite doesn't have a column the model now expects" bug (hit twice
already: prompt_sent/raw_response, then provider_mode/provider_detail)."""

import sqlite3
import uuid

from sqlmodel import Session, select

from text_as_data.db import CodebookRecord, ExtractionRecord, RunRecord, get_engine


def _temp_sqlite_url(tmp_path) -> str:
    path = tmp_path / f"{uuid.uuid4().hex}.sqlite"
    return f"sqlite:///{path}"


def test_get_engine_adds_missing_columns_to_an_existing_table(tmp_path):
    url = _temp_sqlite_url(tmp_path)
    raw_path = url.removeprefix("sqlite:///")

    # Simulate a pre-existing DB file created by an older version of the
    # model -- a "runs" table with none of provider_mode/provider_detail.
    connection = sqlite3.connect(raw_path)
    connection.execute(
        "CREATE TABLE runs ("
        "id INTEGER PRIMARY KEY, codebook_id INTEGER, corpus_id TEXT, "
        "model TEXT, status TEXT, created_at TEXT)"
    )
    connection.execute(
        "INSERT INTO runs (codebook_id, corpus_id, model, status, created_at) "
        "VALUES (1, 'old_corpus', 'old-model', 'done', '2026-01-01T00:00:00')"
    )
    connection.commit()
    connection.close()

    # get_engine() must reconcile the old table shape without losing the
    # row already in it, and without requiring a fresh file.
    engine = get_engine(url)

    with Session(engine) as session:
        loaded = session.exec(select(RunRecord).where(RunRecord.corpus_id == "old_corpus")).first()
        assert loaded is not None
        assert loaded.model == "old-model"
        # New columns exist and fall back to their model-declared defaults
        # for a pre-existing row, rather than erroring or being NULL.
        assert loaded.provider_mode == "api_key"
        assert loaded.provider_detail == ""


def test_get_engine_is_idempotent_on_an_already_current_schema(tmp_path):
    url = _temp_sqlite_url(tmp_path)

    # First call creates the schema at its current (already up to date) shape.
    get_engine(url)
    # Second call against the same file must not error re-adding columns
    # that are already there.
    engine = get_engine(url)

    with Session(engine, expire_on_commit=False) as session:
        codebook = CodebookRecord(name="x", yaml_raw="concept: x")
        session.add(codebook)
        session.commit()
        session.refresh(codebook)

        session.add(RunRecord(codebook_id=codebook.id, corpus_id="c", model="m"))
        session.commit()


def test_get_engine_adds_evidence_verification_columns_to_an_existing_extractions_table(tmp_path):
    url = _temp_sqlite_url(tmp_path)
    raw_path = url.removeprefix("sqlite:///")

    # Simulate a pre-existing DB file created before evidence-span
    # verification existed -- an "extractions" table with none of
    # evidence_verified/evidence_match_tier (or tokens_used/prompt_sent/
    # raw_response, also added later, to keep the simulated old shape
    # realistic rather than just the two columns under test).
    connection = sqlite3.connect(raw_path)
    connection.execute(
        "CREATE TABLE extractions ("
        "id INTEGER PRIMARY KEY, run_id INTEGER, document_id INTEGER, "
        "categoria TEXT, justificativa TEXT, trecho_evidencia TEXT)"
    )
    connection.execute(
        "INSERT INTO extractions (run_id, document_id, categoria, justificativa, trecho_evidencia) "
        "VALUES (1, 1, 'yes', 'because', 'a literal quote')"
    )
    connection.commit()
    connection.close()

    engine = get_engine(url)

    with Session(engine) as session:
        loaded = session.exec(
            select(ExtractionRecord).where(ExtractionRecord.evidence_span == "a literal quote")
        ).first()
        assert loaded is not None
        # New columns exist and fall back to their model-declared defaults
        # for a pre-existing row, rather than erroring or being NULL.
        assert loaded.evidence_verified is False
        assert loaded.evidence_match_tier == ""
        assert loaded.variable == "main"
        assert loaded.variable_spec_hash == ""
        assert loaded.selections_json == ""


def test_get_engine_renames_legacy_portuguese_columns_in_place(tmp_path):
    """A decifra.sqlite written before 2026-09-13 has `categoria`,
    `justificativa`, `trecho_evidencia` on `extractions`. get_engine() must
    rename them to `category`, `rationale`, `evidence_span` without losing
    the row, and must be idempotent (a second get_engine() on the same
    file is a no-op)."""
    url = _temp_sqlite_url(tmp_path)
    raw_path = url.removeprefix("sqlite:///")

    connection = sqlite3.connect(raw_path)
    connection.execute(
        "CREATE TABLE extractions ("
        "id INTEGER PRIMARY KEY, run_id INTEGER, document_id INTEGER, "
        "categoria TEXT, justificativa TEXT, trecho_evidencia TEXT)"
    )
    connection.execute(
        "INSERT INTO extractions (run_id, document_id, categoria, justificativa, trecho_evidencia) "
        "VALUES (1, 1, 'protest', 'because', 'a literal quote')"
    )
    connection.commit()
    connection.close()

    engine = get_engine(url)
    with Session(engine) as session:
        loaded = session.exec(select(ExtractionRecord).where(ExtractionRecord.document_id == 1)).first()
        assert loaded is not None
        assert loaded.category == "protest"
        assert loaded.rationale == "because"
        assert loaded.evidence_span == "a literal quote"

    # Idempotent: building the engine again on the already-migrated file
    # must not raise (no "no such column categoria" from a second RENAME).
    engine_again = get_engine(url)
    with Session(engine_again) as session:
        assert session.exec(select(ExtractionRecord)).first().category == "protest"

    # The old column names are gone, not duplicated alongside the new ones.
    connection = sqlite3.connect(raw_path)
    columns = {row[1] for row in connection.execute('PRAGMA table_info("extractions")').fetchall()}
    connection.close()
    assert {"category", "rationale", "evidence_span"} <= columns
    assert not ({"categoria", "justificativa", "trecho_evidencia"} & columns)


def test_extraction_label_set_handles_single_multi_and_error_rows():
    assert ExtractionRecord(
        run_id=1, document_id=1, category="yes", rationale="r", evidence_span="e"
    ).label_set() == frozenset({"yes"})
    assert ExtractionRecord(
        run_id=1, document_id=1, category="", rationale="r", evidence_span="", selections_json='[{"label":"a"},{"label":"b"}]'
    ).label_set() == frozenset({"a", "b"})
    assert ExtractionRecord(
        run_id=1, document_id=1, category="__error__", rationale="failed", evidence_span="", selections_json="[]"
    ).label_set() == frozenset()
