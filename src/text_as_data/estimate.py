"""Offline estimates: approximate tokens, optional user-supplied prices."""
import hashlib
import json
import math
from sqlmodel import Session, select
from .codebook import Codebook
from .db import DocumentRecord, ExtractionRecord, RunRecord


def estimate_run(session: Session, record, corpus_id: str, model: str, provider_mode: str, bypass_cache: bool, settings) -> dict:
    book = Codebook.from_yaml_string(record.yaml_raw)
    digest = hashlib.sha256(record.yaml_raw.encode("utf-8")).hexdigest()
    documents = session.exec(select(DocumentRecord).where(DocumentRecord.corpus_id == corpus_id)).all()
    cached_ids = set() if bypass_cache else set(session.exec(
        select(ExtractionRecord.document_id).join(RunRecord, ExtractionRecord.run_id == RunRecord.id).where(
            RunRecord.codebook_id == record.id, RunRecord.codebook_yaml_hash == digest,
            RunRecord.model == model, RunRecord.provider_mode == provider_mode,
            ExtractionRecord.categoria != "__error__", ExtractionRecord.original_result_json == "",
        )).all())
    fresh = [doc for doc in documents if doc.id not in cached_ids]
    schema = json.dumps(book.schema.model_json_schema(), ensure_ascii=False)
    tokens = sum(math.ceil((len(json.dumps(book.build_messages(doc.text), ensure_ascii=False)) + len(schema)) / 4) for doc in fresh)
    output = len(fresh) * settings.output_tokens_per_document
    price = None
    if provider_mode == "api_key" and settings.input_usd_per_million is not None and settings.output_usd_per_million is not None:
        price = (tokens * settings.input_usd_per_million + output * settings.output_usd_per_million) / 1_000_000
    return {"documents": len(documents), "cached_documents": len(documents) - len(fresh), "new_documents": len(fresh),
            "input_tokens": tokens, "output_tokens": output, "estimated_usd": price,
            "method": "characters/4 including prompt and JSON schema; approximate; excludes retries",
            "price_source": "user supplied" if price is not None else "unavailable"}
