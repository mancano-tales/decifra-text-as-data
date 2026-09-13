import threading

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from text_as_data.db import CodebookRecord, DocumentRecord, ExtractionRecord, RunRecord, get_engine


def test_round_trip_through_all_four_tables():
    engine = get_engine("sqlite://")

    with Session(engine, expire_on_commit=False) as session:
        codebook = CodebookRecord(name="h1_a", yaml_raw="concept: x")
        session.add(codebook)
        session.commit()
        session.refresh(codebook)

        document = DocumentRecord(corpus_id="v7_pilot", text="some evidence text")
        session.add(document)
        session.commit()
        session.refresh(document)

        run = RunRecord(codebook_id=codebook.id, corpus_id="v7_pilot", model="claude-sonnet-5")
        session.add(run)
        session.commit()
        session.refresh(run)

        extraction = ExtractionRecord(
            run_id=run.id,
            document_id=document.id,
            category="quase_certa",
            rationale="because...",
            evidence_span="the quoted span",
        )
        session.add(extraction)
        session.commit()
        session.refresh(extraction)

    with Session(engine, expire_on_commit=False) as session:
        loaded = session.get(ExtractionRecord, extraction.id)
        assert loaded.category == "quase_certa"
        assert loaded.run_id == run.id
        assert loaded.document_id == document.id

    with Session(engine, expire_on_commit=False) as session:
        loaded_run = session.get(RunRecord, run.id)
        assert loaded_run.status == "pending"
        assert loaded_run.codebook_id == codebook.id


def test_in_memory_engine_is_shared_across_threads():
    # Regression test: sqlite:// with check_same_thread=False alone does NOT
    # share an in-memory database across threads -- each new connection gets
    # its own empty database unless the engine uses StaticPool. This mirrors
    # the FastAPI TestClient + BackgroundTasks pattern (Task 9), where the
    # request/background work runs on a different thread than the test.
    engine = get_engine("sqlite://")
    errors = []

    def write_from_background_thread():
        try:
            with Session(engine, expire_on_commit=False) as session:
                codebook = CodebookRecord(name="from_thread", yaml_raw="concept: x")
                session.add(codebook)
                session.commit()
        except Exception as exc:  # pragma: no cover - captured for the assertion below
            errors.append(exc)

    thread = threading.Thread(target=write_from_background_thread)
    thread.start()
    thread.join()

    assert not errors, f"background thread write failed: {errors}"

    with Session(engine, expire_on_commit=False) as session:
        loaded = session.exec(
            select(CodebookRecord).where(CodebookRecord.name == "from_thread")
        ).first()
        assert loaded is not None
        assert loaded.name == "from_thread"


def test_document_created_at_defaults_to_a_real_timestamp():
    from datetime import datetime

    engine = get_engine("sqlite://")

    with Session(engine, expire_on_commit=False) as session:
        document = DocumentRecord(corpus_id="test_corpus", text="hello")
        session.add(document)
        session.commit()
        session.refresh(document)

    assert isinstance(document.created_at, datetime)


def test_foreign_keys_are_enforced():
    # Regression test: SQLite does not enforce foreign keys unless
    # PRAGMA foreign_keys=ON is set per connection.
    engine = get_engine("sqlite://")

    with Session(engine) as session:
        extraction = ExtractionRecord(
            run_id=999,
            document_id=999,
            category="quase_certa",
            rationale="because...",
            evidence_span="the quoted span",
        )
        session.add(extraction)
        with pytest.raises(IntegrityError):
            session.commit()
