from __future__ import annotations

from typing import Any

import pandas as pd

from .codebook import Codebook

_QUOTE_DASH_FOLD = str.maketrans(
    {
        "‘": "'", "’": "'", "‚": "'",
        "“": '"', "”": '"', "„": '"', "«": '"', "»": '"',
        "–": "-", "—": "-",
    }
)


def _normalize_for_span_match(text: str) -> str:
    """Lowercase, collapse whitespace, and fold curly-quote/dash variants to
    a single canonical form, for the "normalized" tier of
    verify_evidence_span. Must accept a model's evidence quote back even
    when it re-typed smart quotes/em-dashes or spaced things differently
    than the source document, without accepting a genuinely different
    quote -- mirrors QualiHolo's normalizeMap() (see issue #2)."""
    return " ".join(text.translate(_QUOTE_DASH_FOLD).lower().split())


def verify_evidence_span(span: str, document_text: str) -> tuple[bool, str]:
    """Check whether `span` is a verbatim quote from `document_text`.

    Two tiers, in order, porting QualiHolo's verifySpan() design (credited
    in issue #2, ported here because the LLM's evidence_span field --
    `codebook.py` calls it a "Verbatim quote from the document that grounds
    the decision" -- was, until now, never actually checked against the
    source, so a hallucinated or paraphrased quote passed through as if it
    were verbatim):

    1. Exact substring match against `document_text`.
    2. If that fails, both strings are normalized (quotes/dashes folded,
       whitespace collapsed, lowercased) and the substring match is
       retried -- this accepts a model's cosmetic re-typing of the quote
       without accepting a genuinely different one.

    Never falls back to fuzzy/similarity matching: a near-miss quote is
    not verifiable and must not be recorded as if it were.

    Returns (verified, tier), where tier is one of "exact", "normalized",
    "empty", "too_short", or "not_found".
    """
    span = span.strip()
    if not span:
        return False, "empty"
    if span in document_text:
        return True, "exact"
    normalized_span = _normalize_for_span_match(span)
    if len(normalized_span) < 8:
        return False, "too_short"
    if normalized_span in _normalize_for_span_match(document_text):
        return True, "normalized"
    return False, "not_found"


def extract(
    texts: pd.DataFrame,
    codebook: Codebook,
    client: Any,
    model: str,
    id_col: str = "id",
    text_col: str = "text",
) -> pd.DataFrame:
    """Classify each row of `texts` against `codebook` using an instructor client.

    `client` is an `instructor`-patched LLM client (any provider instructor
    supports). One request is made per row; each response is validated
    against `codebook.schema` before being flattened into the output table.
    """
    rows = []
    for _, row in texts.iterrows():
        result = client.chat.completions.create(
            model=model,
            response_model=codebook.schema,
            messages=codebook.build_messages(row[text_col]),
        )
        rows.append({id_col: row[id_col], **result.model_dump()})
    return pd.DataFrame(rows)


import hashlib
import json
import logging

from sqlmodel import Session, select
from tenacity import retry, stop_after_attempt, wait_exponential

from .db import CodebookRecord, DocumentRecord, ExtractionRecord, RunRecord
from .providers import Provider

logger = logging.getLogger(__name__)

ERROR_CATEGORIA = "__error__"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10), reraise=True)
def _extract_with_retry(provider: Provider, messages: list[dict], schema):
    return provider.extract(messages, schema)


def run_extraction(engine, run_id: int, provider: Provider, include_persona: bool = True) -> None:
    """Execute a run: for every document in the run's corpus, reuse a cached
    extraction if one exists for the same (document, codebook, model), else
    call the provider (with retry) and persist the result. A single
    document's failure is recorded as an error row, not a crash of the
    whole run. A failure *outside* the per-document loop (bad codebook
    YAML, a database error) marks the run's own status as "error" instead
    of leaving it stuck at "running" forever — this is the caller's
    (`app.py`'s `BackgroundTasks`) only signal that something went wrong,
    since a background task's exception is otherwise just logged and
    dropped by the ASGI server.

    `include_persona` (default True, matching prior behavior) is passed
    straight through to `Codebook.build_messages` -- exists for prompt-
    design experiments (e.g. ablating the fixed persona line) that want
    run_extraction's caching/retry/persistence machinery without also
    wanting the persona text. Not exposed via `app.py`/`CreateRunRequest`;
    a real research run always wants it on."""
    with Session(engine) as session:
        run = session.get(RunRecord, run_id)
        if run is None:
            raise ValueError(f"run_extraction called with unknown run_id={run_id!r}")

        run.status = "running"
        session.add(run)
        session.commit()

        try:
            codebook_record = session.get(CodebookRecord, run.codebook_id)
            codebook = Codebook.from_yaml_string(codebook_record.yaml_raw)
            codebook_yaml_hash = hashlib.sha256(codebook_record.yaml_raw.encode("utf-8")).hexdigest()
            run.codebook_yaml_hash = codebook_yaml_hash
            session.add(run)
            session.commit()

            documents = session.exec(
                select(DocumentRecord).where(DocumentRecord.corpus_id == run.corpus_id)
            ).all()

            for document in documents:
                # A reproducibility-verification run (bypass_cache=True)
                # must never see a cached hit -- serving a prior run's
                # cached answer back would make "run it again" always
                # agree with itself by construction, defeating the whole
                # point of testing whether the LLM's own output is stable.
                tokens_used = None
                cached = None
                if not run.bypass_cache:
                    cached = session.exec(
                        select(ExtractionRecord)
                        .join(RunRecord, ExtractionRecord.run_id == RunRecord.id)
                        .where(
                            ExtractionRecord.document_id == document.id,
                            # Matching on the codebook's actual content hash,
                            # not codebook_id alone -- a codebook can be
                            # edited in place (same id, new yaml_raw), and a
                            # cache hit keyed only on the id would silently
                            # reuse extractions produced under the *old*
                            # definition. RunRecord.codebook_id is still
                            # required in the join so an unrelated codebook
                            # that happens to hash-collide (practically
                            # impossible with sha256, but free to assert)
                            # can never match.
                            RunRecord.codebook_id == run.codebook_id,
                            RunRecord.codebook_yaml_hash == codebook_yaml_hash,
                            RunRecord.model == run.model,
                            RunRecord.provider_mode == run.provider_mode,
                            ExtractionRecord.original_result_json == "",
                            ExtractionRecord.categoria != ERROR_CATEGORIA,
                        )
                        .order_by(ExtractionRecord.id.desc())
                    ).first()

                if cached is not None:
                    tokens_used = 0
                    categoria, justificativa, trecho = (
                        cached.categoria,
                        cached.justificativa,
                        cached.trecho_evidencia,
                    )
                    evidence_verified, evidence_match_tier = (
                        cached.evidence_verified,
                        cached.evidence_match_tier,
                    )
                    prompt_sent, raw_response = cached.prompt_sent, cached.raw_response
                else:
                    # Best-effort fallback if build_messages succeeds but the
                    # provider call itself fails: still record what was
                    # *going* to be sent, even without the provider's own
                    # (more precise, e.g. CLI-schema-suffixed) prompt string.
                    prompt_sent, raw_response = "", ""
                    try:
                        messages = codebook.build_messages(document.text, include_persona=include_persona)
                        prompt_sent = json.dumps(messages, ensure_ascii=False)
                        result = _extract_with_retry(provider, messages, codebook.schema)
                        categoria, justificativa, trecho = (
                            result.parsed.categoria,
                            result.parsed.justificativa,
                            result.parsed.trecho_evidencia,
                        )
                        prompt_sent, raw_response = result.prompt, result.raw_response
                        tokens_used = result.tokens_used
                    except Exception as exc:  # noqa: BLE001 -- one bad document must not kill the run
                        # A subprocess.TimeoutExpired's str() includes
                        # whatever partial stdout/stderr was captured before
                        # the kill -- for a CLI provider that can be large,
                        # and it would otherwise land verbatim in this TEXT
                        # column. Truncated defensively for any exception
                        # type, not just that one.
                        error_message = str(exc)
                        if len(error_message) > 2000:
                            error_message = error_message[:2000] + "... [truncated]"
                        categoria, justificativa, trecho = ERROR_CATEGORIA, error_message, ""

                    evidence_verified, evidence_match_tier = verify_evidence_span(trecho, document.text)

                session.add(
                    ExtractionRecord(
                        run_id=run.id,
                        document_id=document.id,
                        categoria=categoria,
                        justificativa=justificativa,
                        trecho_evidencia=trecho,
                        evidence_verified=evidence_verified,
                        evidence_match_tier=evidence_match_tier,
                        prompt_sent=prompt_sent,
                        raw_response=raw_response,
                        tokens_used=tokens_used,
                    )
                )
                session.commit()
        except Exception:
            logger.exception("run_extraction failed outside the per-document loop (run_id=%s)", run_id)
            run.status = "error"
            session.add(run)
            session.commit()
            raise

        run.status = "done"
        session.add(run)
        session.commit()
