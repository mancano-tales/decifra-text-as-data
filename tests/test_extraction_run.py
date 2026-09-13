import pytest
from pydantic import BaseModel
from sqlmodel import Session, select

from text_as_data.codebook import Codebook
from text_as_data.db import CodebookRecord, DocumentRecord, ExtractionRecord, RunRecord, get_engine
from text_as_data.extraction import ERROR_CATEGORY, run_extraction
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


class CountingFakeProvider(Provider):
    def __init__(self):
        self.calls = 0

    def extract(self, messages, schema):
        self.calls += 1
        parsed = schema(category="yes", rationale="because", evidence_span="quote")
        return ProviderResult(parsed=parsed, prompt="fake prompt", raw_response="fake raw response")


class AlwaysFailingProvider(Provider):
    def __init__(self, message: str = "rate limited: 429"):
        self.calls = 0
        self._message = message

    def extract(self, messages, schema):
        self.calls += 1
        raise ValueError(self._message)


def _seed(engine, n_documents: int = 2) -> tuple[int, str]:
    with Session(engine) as session:
        codebook = CodebookRecord(name="test", yaml_raw=YAML_SOURCE)
        session.add(codebook)
        session.commit()
        session.refresh(codebook)

        for i in range(n_documents):
            session.add(DocumentRecord(corpus_id="test_corpus", text=f"document {i}"))
        session.commit()

        run = RunRecord(codebook_id=codebook.id, corpus_id="test_corpus", model="fake-model")
        session.add(run)
        session.commit()
        session.refresh(run)
        return run.id, run.corpus_id


def test_run_extraction_creates_one_extraction_per_document_and_marks_run_done():
    engine = get_engine("sqlite://")
    run_id, _ = _seed(engine, n_documents=2)
    provider = CountingFakeProvider()

    run_extraction(engine, run_id, provider)

    with Session(engine) as session:
        extractions = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == run_id)).all()
        run = session.get(RunRecord, run_id)
        assert len(extractions) == 2
        assert all(e.category == "yes" for e in extractions)
        assert run.status == "done"
    assert provider.calls == 2


def test_run_extraction_reuses_cached_extraction_for_same_document_codebook_model():
    engine = get_engine("sqlite://")
    run_id, corpus_id = _seed(engine, n_documents=1)
    provider = CountingFakeProvider()
    run_extraction(engine, run_id, provider)

    with Session(engine) as session:
        codebook_id = session.exec(select(RunRecord).where(RunRecord.id == run_id)).one().codebook_id
        second_run = RunRecord(codebook_id=codebook_id, corpus_id=corpus_id, model="fake-model")
        session.add(second_run)
        session.commit()
        session.refresh(second_run)
        second_run_id = second_run.id

    run_extraction(engine, second_run_id, provider)

    with Session(engine) as session:
        extractions = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == second_run_id)).all()
        assert len(extractions) == 1
    assert provider.calls == 1  # not called again for the second run — cache hit


def test_run_extraction_records_real_error_message_and_still_marks_run_done():
    engine = get_engine("sqlite://")
    run_id, _ = _seed(engine, n_documents=1)
    provider = AlwaysFailingProvider(message="rate limited: 429")

    run_extraction(engine, run_id, provider)

    with Session(engine) as session:
        extractions = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == run_id)).all()
        run = session.get(RunRecord, run_id)
        assert len(extractions) == 1
        assert extractions[0].category == ERROR_CATEGORY
        # The real error message must survive, not a tenacity RetryError wrapper.
        assert extractions[0].rationale == "rate limited: 429"
        assert "RetryError" not in extractions[0].rationale
        assert run.status == "done"
    assert provider.calls == 3  # retried up to the stop_after_attempt(3) limit


def test_run_extraction_records_prompt_too_long_as_readable_per_document_error(monkeypatch):
    # Regression for the third Windows-specific CliProvider bug: in
    # prompt_mode="arg" a long document used to die inside subprocess.run
    # with `FileNotFoundError: [WinError 206]`. The provider now raises
    # PromptTooLongError before spawning anything; this test proves that
    # error lands in the Results table as an actionable per-document row
    # (not a crashed run), via the same catch-all path as any other
    # provider failure. Uses the real CliProvider, not a fake.
    import shutil

    from text_as_data.providers import CliProvider

    monkeypatch.setattr(shutil, "which", lambda name: None)

    def never_called_runner(command, input, capture_output, encoding, timeout):
        raise AssertionError("CLI must not be spawned when the prompt cannot fit on the command line")

    engine = get_engine("sqlite://")
    run_id, _ = _seed(engine, n_documents=1)
    provider = CliProvider(command=["agy", "-p"], runner=never_called_runner, prompt_mode="arg", max_arg_length=200)

    run_extraction(engine, run_id, provider)

    with Session(engine) as session:
        extractions = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == run_id)).all()
        run = session.get(RunRecord, run_id)
        assert len(extractions) == 1
        assert extractions[0].category == ERROR_CATEGORY
        assert "too long for the command line" in extractions[0].rationale
        assert "limit 200" in extractions[0].rationale
        assert "stdin" in extractions[0].rationale
        assert run.status == "done"


def test_run_extraction_truncates_a_huge_error_message():
    # A subprocess.TimeoutExpired's str() includes whatever partial
    # stdout/stderr was captured before the kill -- for a CLI provider that
    # can be large. Nothing should land verbatim in the rationale
    # column at unbounded length, regardless of exception type.
    engine = get_engine("sqlite://")
    run_id, _ = _seed(engine, n_documents=1)
    huge_message = "x" * 5000
    provider = AlwaysFailingProvider(message=huge_message)

    run_extraction(engine, run_id, provider)

    with Session(engine) as session:
        extraction = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == run_id)).first()
        assert extraction.category == ERROR_CATEGORY
        assert len(extraction.rationale) < len(huge_message)
        assert extraction.rationale.endswith("[truncated]")


def test_run_extraction_does_not_treat_error_row_as_cached():
    engine = get_engine("sqlite://")
    run_id, corpus_id = _seed(engine, n_documents=1)
    failing_provider = AlwaysFailingProvider()
    run_extraction(engine, run_id, failing_provider)
    assert failing_provider.calls == 3

    with Session(engine) as session:
        codebook_id = session.exec(select(RunRecord).where(RunRecord.id == run_id)).one().codebook_id
        second_run = RunRecord(codebook_id=codebook_id, corpus_id=corpus_id, model="fake-model")
        session.add(second_run)
        session.commit()
        session.refresh(second_run)
        second_run_id = second_run.id

    succeeding_provider = CountingFakeProvider()
    run_extraction(engine, second_run_id, succeeding_provider)

    # The prior __error__ row must not be reused as a cache hit — the
    # provider must be called again for the second run.
    assert succeeding_provider.calls == 1
    with Session(engine) as session:
        extractions = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == second_run_id)).all()
        assert len(extractions) == 1
        assert extractions[0].category == "yes"


def test_run_extraction_records_build_messages_failure_as_error_row_without_crashing(monkeypatch):
    def _raise(self, text, include_persona=True):
        raise ValueError("mojibake broke build_messages")

    monkeypatch.setattr(Codebook, "build_messages", _raise)

    engine = get_engine("sqlite://")
    run_id, _ = _seed(engine, n_documents=2)
    provider = CountingFakeProvider()

    run_extraction(engine, run_id, provider)

    with Session(engine) as session:
        extractions = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == run_id)).all()
        run = session.get(RunRecord, run_id)
        # Both documents get an error row instead of crashing the run.
        assert len(extractions) == 2
        assert all(e.category == ERROR_CATEGORY for e in extractions)
        assert all(e.rationale == "mojibake broke build_messages" for e in extractions)
        assert run.status == "done"  # not stuck at "running"
    # build_messages fails before provider.extract is ever reached, and a
    # build_messages failure must not be pointlessly retried.
    assert provider.calls == 0


def test_run_extraction_persists_prompt_and_raw_response_on_success():
    engine = get_engine("sqlite://")
    run_id, _ = _seed(engine, n_documents=1)

    run_extraction(engine, run_id, CountingFakeProvider())

    with Session(engine) as session:
        extraction = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == run_id)).one()
        assert extraction.prompt_sent == "fake prompt"
        assert extraction.raw_response == "fake raw response"


def test_run_extraction_persists_best_effort_prompt_on_provider_failure():
    # No ProviderResult exists when the provider itself raises -- but the
    # messages that were *going* to be sent are still known (build_messages
    # already succeeded), so that much is worth recording rather than
    # leaving the audit trail empty.
    engine = get_engine("sqlite://")
    run_id, _ = _seed(engine, n_documents=1)

    run_extraction(engine, run_id, AlwaysFailingProvider())

    with Session(engine) as session:
        extraction = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == run_id)).one()
        assert extraction.category == ERROR_CATEGORY
        assert extraction.prompt_sent != ""
        assert "document 0" in extraction.prompt_sent


def test_run_extraction_leaves_prompt_empty_when_build_messages_fails(monkeypatch):
    def _raise(self, text, include_persona=True):
        raise ValueError("mojibake broke build_messages")

    monkeypatch.setattr(Codebook, "build_messages", _raise)

    engine = get_engine("sqlite://")
    run_id, _ = _seed(engine, n_documents=1)

    run_extraction(engine, run_id, CountingFakeProvider())

    with Session(engine) as session:
        extraction = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == run_id)).one()
        assert extraction.prompt_sent == ""


def test_run_extraction_copies_prompt_and_raw_response_from_cached_extraction():
    engine = get_engine("sqlite://")
    run_id, corpus_id = _seed(engine, n_documents=1)
    run_extraction(engine, run_id, CountingFakeProvider())

    with Session(engine) as session:
        codebook_id = session.exec(select(RunRecord).where(RunRecord.id == run_id)).one().codebook_id
        second_run = RunRecord(codebook_id=codebook_id, corpus_id=corpus_id, model="fake-model")
        session.add(second_run)
        session.commit()
        session.refresh(second_run)
        second_run_id = second_run.id

    # A different fake, never called (cache hit) -- if the cached
    # prompt_sent/raw_response weren't copied over, this run's row would
    # end up with empty audit fields despite reusing a real extraction.
    run_extraction(engine, second_run_id, CountingFakeProvider())

    with Session(engine) as session:
        extraction = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == second_run_id)).one()
        assert extraction.prompt_sent == "fake prompt"
        assert extraction.raw_response == "fake raw response"


def test_run_extraction_does_not_reuse_cache_after_codebook_is_edited_in_place():
    # PUT /codebooks/{id} edits a CodebookRecord's yaml_raw in place, same
    # id -- a cache match keyed only on codebook_id would otherwise reuse
    # an extraction produced under the codebook's *previous* definition,
    # silently ignoring the edit the researcher just made.
    engine = get_engine("sqlite://")
    run_id, corpus_id = _seed(engine, n_documents=1)
    provider = CountingFakeProvider()
    run_extraction(engine, run_id, provider)
    assert provider.calls == 1

    with Session(engine) as session:
        run = session.exec(select(RunRecord).where(RunRecord.id == run_id)).one()
        codebook_id = run.codebook_id
        codebook = session.get(CodebookRecord, codebook_id)
        # Edit the codebook's definition in place -- same id, new content.
        codebook.yaml_raw = codebook.yaml_raw.replace("Positive case.", "Positive case (edited).")
        session.add(codebook)
        session.commit()

        second_run = RunRecord(codebook_id=codebook_id, corpus_id=corpus_id, model="fake-model")
        session.add(second_run)
        session.commit()
        session.refresh(second_run)
        second_run_id = second_run.id

    run_extraction(engine, second_run_id, provider)

    # The edited codebook must trigger a fresh provider call, not reuse the
    # extraction cached under the pre-edit definition.
    assert provider.calls == 2
    with Session(engine) as session:
        extractions = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == second_run_id)).all()
        assert len(extractions) == 1


def test_run_extraction_records_the_codebook_yaml_hash_on_the_run():
    engine = get_engine("sqlite://")
    run_id, _ = _seed(engine, n_documents=1)

    run_extraction(engine, run_id, CountingFakeProvider())

    with Session(engine) as session:
        run = session.get(RunRecord, run_id)
        assert run.codebook_yaml_hash != ""


def test_run_extraction_raises_clear_error_for_unknown_run_id():
    engine = get_engine("sqlite://")

    with pytest.raises(ValueError, match="unknown run_id"):
        run_extraction(engine, 999, CountingFakeProvider())


def test_run_extraction_marks_run_as_error_on_setup_failure_instead_of_hanging():
    engine = get_engine("sqlite://")
    with Session(engine) as session:
        codebook = CodebookRecord(name="broken", yaml_raw="this is not: [valid, codebook, yaml: at all")
        session.add(codebook)
        session.commit()
        session.refresh(codebook)

        session.add(DocumentRecord(corpus_id="test_corpus", text="document 0"))
        session.commit()

        run = RunRecord(codebook_id=codebook.id, corpus_id="test_corpus", model="fake-model")
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id

    with pytest.raises(Exception):  # noqa: B017 -- exact exception type is YAML-parser-dependent
        run_extraction(engine, run_id, CountingFakeProvider())

    with Session(engine) as session:
        run = session.get(RunRecord, run_id)
        # Not stuck at "running" forever, and not silently "done" either.
        assert run.status == "error"


class QuotingFakeProvider(Provider):
    """Returns a evidence_span that is an exact substring of whatever
    document text it's asked to classify -- for testing the "verified"
    path of run_extraction's evidence-span check without hand-writing the
    document text to match a hardcoded quote."""

    def extract(self, messages, schema):
        document_text = messages[-1]["content"]
        quote = document_text[:12]  # long enough to clear the too_short cutoff
        parsed = schema(category="yes", rationale="because", evidence_span=quote)
        return ProviderResult(parsed=parsed, prompt="fake prompt", raw_response="fake raw response")


class FabricatingFakeProvider(Provider):
    """Always returns a evidence_span that is long enough to clear the
    too_short cutoff but never actually appears in the document text -- the
    fabricated/paraphrased-quote case verify_evidence_span exists to
    catch, distinct from CountingFakeProvider's "quote" (which is too
    short to reach the not_found tier at all -- see the too_short test in
    tests/test_evidence_verification.py)."""

    def extract(self, messages, schema):
        parsed = schema(
            category="yes",
            rationale="because",
            evidence_span="this exact sentence never appears in the source document",
        )
        return ProviderResult(parsed=parsed, prompt="fake prompt", raw_response="fake raw response")


def test_run_extraction_records_verified_true_and_exact_tier_for_a_real_quote():
    engine = get_engine("sqlite://")
    run_id, _ = _seed(engine, n_documents=1)
    run_extraction(engine, run_id, QuotingFakeProvider())

    with Session(engine) as session:
        extraction = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == run_id)).one()
        assert extraction.evidence_verified is True
        assert extraction.evidence_match_tier == "exact"


def test_run_extraction_records_verified_false_for_a_fabricated_quote():
    engine = get_engine("sqlite://")
    run_id, _ = _seed(engine, n_documents=1)
    run_extraction(engine, run_id, FabricatingFakeProvider())

    with Session(engine) as session:
        extraction = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == run_id)).one()
        assert extraction.evidence_verified is False
        assert extraction.evidence_match_tier == "not_found"


def test_run_extraction_copies_verification_result_on_cache_hit_instead_of_recomputing():
    engine = get_engine("sqlite://")
    run_id, corpus_id = _seed(engine, n_documents=1)
    run_extraction(engine, run_id, QuotingFakeProvider())

    with Session(engine) as session:
        codebook_id = session.exec(select(RunRecord).where(RunRecord.id == run_id)).one().codebook_id
        second_run = RunRecord(codebook_id=codebook_id, corpus_id=corpus_id, model="fake-model")
        session.add(second_run)
        session.commit()
        session.refresh(second_run)
        second_run_id = second_run.id

    # A provider that would fail verification if it were actually called --
    # proves the cache hit path copies the prior result rather than
    # recomputing (or, worse, calling the provider again).
    run_extraction(engine, second_run_id, CountingFakeProvider())

    with Session(engine) as session:
        extraction = session.exec(
            select(ExtractionRecord).where(ExtractionRecord.run_id == second_run_id)
        ).one()
        assert extraction.evidence_verified is True
        assert extraction.evidence_match_tier == "exact"
