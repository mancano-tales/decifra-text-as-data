from sqlmodel import Session

from text_as_data.db import CodebookRecord, DocumentRecord, ExtractionRecord, RunRecord, get_engine
from text_as_data.disclosure import build_disclosure

YAML_SOURCE = """
concept: protest
description: "A collective public event."
categories:
  - label: protest
    definition: "An occupation, march, or strike."
  - label: not_protest
    definition: "Any event that does not meet the criteria above."
"""


def _make_run(provider_mode: str = "api_key", provider_detail: str = "claude-sonnet-5"):
    engine = get_engine("sqlite://")
    with Session(engine, expire_on_commit=False) as session:
        codebook = CodebookRecord(name="protest", yaml_raw=YAML_SOURCE)
        session.add(codebook)
        session.commit()
        session.refresh(codebook)

        document = DocumentRecord(corpus_id="demo", text="About 200 people occupied the square.")
        session.add(document)
        session.commit()
        session.refresh(document)

        run = RunRecord(
            codebook_id=codebook.id,
            corpus_id="demo",
            model="claude-sonnet-5",
            provider_mode=provider_mode,
            provider_detail=provider_detail,
        )
        session.add(run)
        session.commit()
        session.refresh(run)

        session.add(
            ExtractionRecord(
                run_id=run.id,
                document_id=document.id,
                category="protest",
                rationale="because",
                evidence_span="occupied the square",
                prompt_sent='[{"role": "system", "content": "..."}]',
                raw_response='{"category": "protest"}',
            )
        )
        session.commit()

    return session, run


def test_disclosure_covers_all_guide_llm_sections():
    session, run = _make_run()

    report = build_disclosure(session, run)

    for section in ("A_purpose_and_application", "B_model_and_access_details", "C_prompting",
                     "D_data_handling", "E_output_processing", "F_reproducibility", "G_conflicts_and_support"):
        assert section in report, f"missing GUIDE-LLM section: {section}"


def test_disclosure_reports_api_key_mode_correctly():
    session, run = _make_run(provider_mode="api_key", provider_detail="claude-sonnet-5")

    report = build_disclosure(session, run)

    assert report["B_model_and_access_details"]["B1_model_name_provider_version_date"]["provider_mode"] == "api_key"
    assert "function/tool calling" in report["E_output_processing"]["E2_postprocessing"]


def test_disclosure_reports_cli_mode_correctly():
    session, run = _make_run(provider_mode="cli", provider_detail="claude -p")

    report = build_disclosure(session, run)

    b1 = report["B_model_and_access_details"]["B1_model_name_provider_version_date"]
    assert b1["provider_mode"] == "cli"
    assert b1["provider_detail"] == "claude -p"
    assert "Best-effort" in report["E_output_processing"]["E2_postprocessing"]


def test_disclosure_is_honest_about_unvalidated_output():
    session, run = _make_run()

    report = build_disclosure(session, run)

    assert "unvalidated" in report["E_output_processing"]["E1_human_validation"]


def test_disclosure_run_summary_counts_documents_and_errors():
    session, run = _make_run()

    report = build_disclosure(session, run)

    assert report["run_summary"] == {"total_documents": 1, "processed_documents": 1, "error_documents": 0}
