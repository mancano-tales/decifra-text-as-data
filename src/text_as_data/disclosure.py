from __future__ import annotations

from sqlmodel import Session, select

from .codebook import spec_from_yaml_string
from .db import CodebookRecord, DocumentRecord, ExtractionRecord, RunRecord

# Decifra's own software version isn't tracked as a release number anywhere
# yet (see AGENTS.md's build-order notes -- this is still pre-1.0, slice by
# slice); the git commit is the only thing that actually identifies "what
# code produced this run" today.
GUIDE_LLM_URL = "https://llm-checklist.com/"

_PARSING_METHOD_BY_PROVIDER_MODE = {
    "api_key": (
        "Structured output enforced at the API level via function/tool calling "
        "(the `instructor` library) -- the provider cannot return a response that "
        "doesn't validate against the codebook's schema."
    ),
    "cli": (
        "Best-effort: the schema is described in the prompt, not enforced by the "
        "provider. The response is scanned for the first top-level JSON object "
        "that validates against the schema; malformed output is retried up to 3 "
        "times before the document is recorded as an error row. See AGENTS.md's "
        "provider layer design for why this mode exists and its known reliability "
        "tradeoff versus API-key mode."
    ),
}


def _git_commit() -> str | None:
    """Best-effort short commit hash for the code that produced this run.
    Returns None (not an exception) outside a git checkout -- a packaged
    install has no .git directory, and a disclosure report missing this one
    field is still useful."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            encoding="utf-8",
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def build_disclosure(session: Session, run: RunRecord) -> dict:
    """Build a GUIDE-LLM-shaped AI-use disclosure report for one run.

    GUIDE-LLM (Feuerriegel et al., a consensus checklist from 80+ researchers
    across psychology/economics/sociology/AI/ethics for reporting LLM use in
    behavioral and social science research -- see llm-checklist.com) asks 13
    specific questions grouped into 7 sections (A-G). This maps each one onto
    what Decifra actually knows about a run, rather than a generic AI-use
    paragraph -- and says so honestly where Decifra doesn't track something,
    instead of leaving the question unanswered or guessing.

    This is deliberately a *report*, not a form the researcher fills in: the
    whole point of GUIDE-LLM per its own philosophy ("does not tell
    researchers how to use AI... establishes a minimum standard for
    transparency") is that these facts should be recoverable from what the
    software actually did, not reconstructed from memory afterward.
    """
    codebook = session.get(CodebookRecord, run.codebook_id)
    spec = spec_from_yaml_string(codebook.yaml_raw) if codebook else None

    extractions = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == run.id)).all()
    total_documents = len(
        session.exec(select(DocumentRecord).where(DocumentRecord.corpus_id == run.corpus_id)).all()
    )
    error_count = sum(1 for e in extractions if e.category == "__error__")

    provider_label = "Anthropic/OpenAI API (via instructor)" if run.provider_mode == "api_key" else "local CLI"

    return {
        "run_id": run.id,
        "generated_for_status": run.status,
        "guide_llm_reference": {
            "checklist": "GUIDE-LLM",
            "url": GUIDE_LLM_URL,
            "note": (
                "Consensus reporting checklist for LLM use in behavioral/social "
                "science research (Feuerriegel et al.). This report answers its "
                "13 items from A to G using what Decifra recorded for this run."
            ),
        },
        "A_purpose_and_application": {
            "A1_purpose": (
                f"LLM used to categorize each document in corpus {run.corpus_id!r} into one of the "
                f"categories of the {spec['concept']!r} codebook, per a researcher-authored coding scheme."
                if spec
                else f"LLM used to categorize each document in corpus {run.corpus_id!r} (codebook record missing)."
            ),
            "A2_human_in_the_loop": (
                "Per-document categorization is fully automated (unattended batch run, no human review during "
                "execution). The codebook that defines the categories is human-authored, and Decifra's own design "
                "treats every automated result as provisional until validated against a human-coded gold sample "
                "(see AGENTS.md, \"Why the validation step is not optional\") -- see section E for whether that "
                "validation has actually been done for this codebook."
            ),
        },
        "B_model_and_access_details": {
            "B1_model_name_provider_version_date": {
                "model": run.model,
                "provider_mode": run.provider_mode,
                "provider_detail": run.provider_detail,
                "run_created_at": run.created_at.isoformat() if run.created_at else None,
                "cifra_git_commit": _git_commit(),
            },
            "B2_access_mode": f"{provider_label}; each document is one independent request (see B5).",
            "B3_parameters": (
                "Not explicitly configured by Decifra (temperature, max_tokens, seed) -- provider/library defaults "
                "apply. Not tracked per-run in this version; a fixed, disclosed default would need to be set "
                "explicitly in providers.py before this could report a real value instead of this note."
            ),
            "B4_finetuning": "None. No fine-tuned or customized model is used at any point in Decifra's pipeline.",
            "B5_session_state": (
                "No. Each document is a stateless, independent call: build_messages() constructs a fresh "
                "prompt from the codebook and that document's text alone, with no memory of prior documents "
                "in the run."
            ),
        },
        "C_prompting": {
            "C1_exact_prompts": (
                f"Recorded per document. {len(extractions)} of {total_documents} documents in this run have "
                "a persisted `prompt_sent` (the literal messages sent, including the system role) retrievable "
                "via GET /runs/{run_id}/results -- this is the audit trail, not a reconstruction."
            ),
            "C2_system_instructions": (
                "Derived from the codebook: a fixed preamble instructing the model to follow the coding scheme "
                "exactly, followed by the codebook's own concept/category definitions, examples, and boundary "
                "notes verbatim (see Codebook.build_messages in codebook.py). Included in each row's C1 prompt."
            ),
        },
        "D_data_handling": {
            "D1_personal_sensitive_data": (
                "No automatic PII detection, redaction, or anonymization. The document text sent to the "
                "provider is exactly what was imported into the corpus -- the researcher is responsible for "
                "screening corpus content before running extraction, per AGENTS.md's stated limits."
            ),
        },
        "E_output_processing": {
            "E1_human_validation": (
                "Not recorded for this run: Decifra does not yet persist a link between a run and a human-coded "
                "gold-label validation result for its codebook (the Validation screen, AGENTS.md's Screen 5, is "
                "still being built as of this report). Treat this run's output as unvalidated until a kappa/"
                "precision/recall check against a human-coded sample has actually been run for this codebook."
            ),
            "E2_postprocessing": _PARSING_METHOD_BY_PROVIDER_MODE[run.provider_mode],
        },
        "F_reproducibility": {
            "F1_code_and_scripts": (
                "Full pipeline is open source: github.com/ (see this repo's own remote). "
                f"Codebook YAML: `codebooks/{run.codebook_id}` (GET /codebooks/{run.codebook_id}). "
                f"Run parameters: GET /runs/{run.id}. Decifra commit: {_git_commit() or 'unknown (no git checkout)'}."
            ),
        },
        "G_conflicts_and_support": {
            "G1_funding_support": (
                "Not applicable at the software level -- Decifra has no funding/support relationship with any "
                "provider. Report your own funding and provider account relationships (e.g. institutional API "
                "credits) in your paper's own disclosures."
            ),
        },
        "run_summary": {
            "total_documents": total_documents,
            "processed_documents": len(extractions),
            "error_documents": error_count,
        },
    }
