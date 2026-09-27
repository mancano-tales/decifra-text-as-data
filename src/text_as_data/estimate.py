"""Offline estimates: approximate tokens, optional user-supplied prices."""
import json
import math

from sqlmodel import Session, select

from .codebook import Codebook
from .db import DocumentRecord, ExtractionRecord, RunRecord


def estimate_run(
    session: Session,
    record,
    corpus_id: str,
    model: str,
    provider_mode: str,
    bypass_cache: bool,
    settings,
) -> dict:
    book = Codebook.from_yaml_string(record.yaml_raw)
    documents = session.exec(select(DocumentRecord).where(DocumentRecord.corpus_id == corpus_id)).all()
    if book.prompt_strategy != "per_variable":
        raise NotImplementedError("prompt_strategy='joint' estimates are deferred to R1.1 step 8")
    cached_pairs: set[tuple[int, str, str]] = set()
    if not bypass_cache:
        cached_pairs = set(
            session.exec(
                select(
                    ExtractionRecord.document_id,
                    ExtractionRecord.variable,
                    ExtractionRecord.variable_spec_hash,
                )
                .join(RunRecord, ExtractionRecord.run_id == RunRecord.id)
                .where(
                    RunRecord.codebook_id == record.id,
                    RunRecord.model == model,
                    RunRecord.provider_mode == provider_mode,
                    ExtractionRecord.category != "__error__",
                    ExtractionRecord.original_result_json == "",
                )
            )
            .all()
        )
    fresh_pairs = [
        (doc, variable)
        for doc in documents
        for variable in book.variables
        if (doc.id, variable.name, variable.spec_hash) not in cached_pairs
    ]
    tokens = 0
    output = 0
    for doc, variable in fresh_pairs:
        schema = json.dumps(variable.schema.model_json_schema(), ensure_ascii=False)
        messages = json.dumps(book.build_messages(doc.text, variable=variable), ensure_ascii=False)
        tokens += math.ceil((len(messages) + len(schema)) / 4)
        output_multiplier = (variable.max_labels or len(variable.categories)) if variable.multi_label else 1
        output += settings.output_tokens_per_document * output_multiplier
    fresh_document_ids = {doc.id for doc, _ in fresh_pairs}
    cached_document_count = sum(doc.id not in fresh_document_ids for doc in documents)
    total_calls = len(documents) * len(book.variables)
    cached_calls = total_calls - len(fresh_pairs)
    price = None
    if (
        provider_mode == "api_key"
        and settings.input_usd_per_million is not None
        and settings.output_usd_per_million is not None
    ):
        price = (tokens * settings.input_usd_per_million + output * settings.output_usd_per_million) / 1_000_000
    return {
        "documents": len(documents),
        "cached_documents": cached_document_count,
        "new_documents": len(fresh_document_ids),
        "total_calls": total_calls,
        "cached_calls": cached_calls,
        "new_calls": len(fresh_pairs),
        "input_tokens": tokens,
        "output_tokens": output,
        "estimated_usd": price,
        "method": (
            "characters/4 per uncached document-variable prompt plus JSON schema; output tokens use the configured "
            "per-document estimate, scaled by max_labels or category count for multi-label variables; approximate; "
            "excludes retries"
        ),
        "price_source": "user supplied" if price is not None else "unavailable",
    }
