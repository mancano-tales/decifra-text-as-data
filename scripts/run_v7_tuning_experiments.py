"""V7 pipeline tuning experiments: persona ablation, reproducibility
repeat, and joint hypothesis-pair scoring -- items 3, 4, 5 from
docs/research/2026-09-02_llm_pipeline_verification_methodology.md's open
items, per the author's explicit request (2026-09-02) to run all three
against the real `agy` CLI rather than reason about them abstractly.

Four conditions on the standard 16-candidate set (see ASSIGNMENTS,
carried over unchanged from scripts/run_v7_candidates_via_agy.py):

  A. baseline    -- current enriched codebook (with tuning item 2's
                    instructions/evidence delimiter), persona on.
  B. no_persona  -- identical codebook and corpus, persona off. Isolates
                    the fixed persona line's own marginal effect (item 4).
  C. repeat      -- identical to A, a second independent call. Tests
                    whether the pipeline's own output is reproducible
                    under the *current* code, not the pre-delimiter-fix
                    baseline the 21/32 finding was measured against
                    (item 5).
  D. joint       -- one call per candidate (not per side) scoring both
                    hypothesis sides at once via
                    pilot_v7.build_joint_hypothesis_messages_and_schema,
                    instead of two separate blind calls (item 3).

A/B/C all set RunRecord.bypass_cache=True: they deliberately share the
same codebook (persona is applied at the build_messages layer, not
baked into codebook YAML, so A/B/C can be the same CodebookRecord) and
the same corpus, so without bypassing the cache, B and C would silently
serve back A's already-committed extractions instead of making a
genuinely independent call -- run_extraction's cache key is
(document, codebook, codebook_hash, model), which does not include
persona or "is this a repeat" as a dimension.

Comparisons (A vs B, A vs C) are computed via validation.py's
agreement_report()/reproducibility_report() -- joined on a
pair_side_fk_id_ev string key, not the raw integer document_id, since
that only has meaning within one condition's own run.

Usage:
    python scripts/run_v7_tuning_experiments.py
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from text_as_data.codebook import spec_to_yaml_string  # noqa: E402
from text_as_data.db import CodebookRecord, DocumentRecord, ExtractionRecord, RunRecord, get_engine  # noqa: E402
from text_as_data.extraction import run_extraction  # noqa: E402
from text_as_data.pilot_v7 import (  # noqa: E402
    HYPOTHESIS_DEFINITIONS,
    build_enriched_hypothesis_codebook_spec,
    build_joint_hypothesis_messages_and_schema,
)
from text_as_data.providers import CliProvider  # noqa: E402
from text_as_data.validation import reproducibility_report  # noqa: E402

SCRATCH = Path(
    "C:/Users/Mancano/AppData/Local/Temp/claude/"
    "C--Users-Mancano-Documents-MancanoSync-text-as-data/"
    "64bf4a45-2f26-4117-8f92-ab0c1cf78c1f/scratchpad"
)

# (fk_id_ev, hypothesis_pair) -- unchanged from run_v7_candidates_via_agy.py
ASSIGNMENTS = [
    ("2013-08-04_FSP_0008_associacao_brasileira_de_mante", "H1"),
    ("2015-06-26_FSP_0022_associacao_brasileira_de_mante", "H1"),
    ("2016-07-16_FSP_0025_associacao_brasileira_de_mante", "H1"),
    ("2017-11-22_FSP_0327_associacao_brasileira_de_mante", "H1"),
    ("2024-02-16_FSP_0306_associacao_brasileira_de_mante", "H1"),
    ("2006-07-04_FSP_0067_eunice_durham_ministerio", "H1"),
    ("2003-12-01_FSP_0047_edson_franco_mantenedoras", "H2"),
    ("2006-05-10_FSP_0066_associacao_brasileira_de_mante", "H2"),
    ("2015-06-27_FSP_0023_associacao_brasileira_de_mante", "H2"),
    ("2022-05-01_FSP_0257_associacao_brasileira_de_mante", "H2"),
    ("2023-08-17_FSP_0262_associacao_brasileira_de_mante", "H2"),
    ("2001-07-23_FSP_0037_eunice_durham_ministerio", "H3"),
    ("2004-02-16_FSP_0055_edson_franco_mantenedoras", "H3"),
    ("2019-06-06_FSP_0274_associacao_brasileira_de_mante", "H3"),
    ("2020-12-01_FSP_0290_associacao_brasileira_de_mante", "H3"),
    ("2024-02-16_FSP_0306_associacao_brasileira_de_mante", "H3"),
]

PAIR_CODES = sorted({pair for _, pair in ASSIGNMENTS})


def seed_documents_and_codebooks(session, docs):
    """One corpus per pair (shared across A/B/C), one codebook per
    (pair, side) (shared across A/B/C -- persona is a run_extraction
    parameter, not baked into the YAML). Returns
    {(pair, side): codebook_id} and {pair: corpus_id}."""
    codebook_ids: dict[tuple[str, str], int] = {}
    corpus_ids: dict[str, str] = {}

    for pair_code in PAIR_CODES:
        corpus_id = f"v7_tuning_{pair_code}"
        corpus_ids[pair_code] = corpus_id
        for fk_id_ev, pair in ASSIGNMENTS:
            if pair != pair_code:
                continue
            d = docs[fk_id_ev]
            doc = DocumentRecord(
                corpus_id=corpus_id,
                text=d["complete_evidence_content"],
                metadata_json=json.dumps({"fk_id_ev": fk_id_ev, "title": d["evidence_title"]}),
            )
            session.add(doc)

        for side_label in ("a", "b"):
            yaml_raw = spec_to_yaml_string(build_enriched_hypothesis_codebook_spec(pair_code, side_label))
            codebook = CodebookRecord(name=f"{pair_code}_{side_label}", yaml_raw=yaml_raw)
            session.add(codebook)
            session.flush()
            codebook_ids[(pair_code, side_label)] = codebook.id

    session.commit()
    return codebook_ids, corpus_ids


def run_condition(engine, provider, condition_name, codebook_ids, corpus_ids, include_persona):
    """Create one RunRecord per (pair, side) against the shared
    codebook/corpus, execute it with bypass_cache=True, return
    {(pair, side): run_id}."""
    run_ids: dict[tuple[str, str], int] = {}
    with Session(engine) as session:
        for (pair_code, side_label), codebook_id in codebook_ids.items():
            run = RunRecord(
                codebook_id=codebook_id,
                corpus_id=corpus_ids[pair_code],
                model=f"agy-gemini-{condition_name}",
                bypass_cache=True,
            )
            session.add(run)
            session.flush()
            run_ids[(pair_code, side_label)] = run.id
        session.commit()

    for (pair_code, side_label), run_id in run_ids.items():
        print(f"--- [{condition_name}] {pair_code} side {side_label} (run_id={run_id}) ---", flush=True)
        t0 = time.time()
        try:
            run_extraction(engine, run_id, provider, include_persona=include_persona)
        except Exception as exc:  # noqa: BLE001 -- report and continue
            print(f"  run {run_id} raised: {exc}")
        print(f"  done in {time.time() - t0:.1f}s", flush=True)

    return run_ids


def hypothesis_full_definition(pair_code: str, side_label: str) -> str:
    """Same shape as scripts/run_v7_candidates_via_agy.py's inline version
    -- kept identical so a reviewer sees the same rendering of a
    hypothesis's mechanism/premises regardless of which script produced
    the row they're looking at. Not a general engine helper (deliberately
    pilot_v7.py/script-local), since 'render this for a human reviewer'
    is a reporting concern, not an extraction one."""
    other_label = "b" if side_label == "a" else "a"
    pair_def = HYPOTHESIS_DEFINITIONS[pair_code]
    this_hyp, other_hyp = pair_def[side_label], pair_def[other_label]
    return (
        f"{this_hyp['name']}\n"
        f"Mechanism: {this_hyp['mechanism']}\n"
        f"Premises: {this_hyp['premises']}\n\n"
        f"Rival hypothesis in this pair: {other_hyp['name']}\n"
        f"Rival mechanism: {other_hyp['mechanism']}"
    )


def extraction_rows(engine, run_ids: dict[tuple[str, str], int]) -> pd.DataFrame:
    """document/extraction rows for one condition, keyed by a
    pair_side_fk_id_ev string -- the only key that has meaning across
    conditions, since raw document_id/run_id are per-condition-local.

    Carries the complete hypothesis definition and the complete evidence
    text alongside every row, not just labels/IDs -- the author's explicit
    requirement for every spreadsheet this pilot produces (AGENTS.md's
    "Real-world pilot data" section, "so a human reviewer never has to
    hunt down source material to check a row"), which the first version
    of this function failed to carry over from
    scripts/run_v7_candidates_via_agy.py despite having just read that
    convention while writing it."""
    rows = []
    with Session(engine) as session:
        for (pair_code, side_label), run_id in run_ids.items():
            extractions = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == run_id)).all()
            for ext in extractions:
                doc = session.get(DocumentRecord, ext.document_id)
                meta = json.loads(doc.metadata_json)
                rows.append(
                    {
                        "key": f"{pair_code}_{side_label}_{meta['fk_id_ev']}",
                        "pair": pair_code,
                        "side": side_label,
                        "fk_id_ev": meta["fk_id_ev"],
                        "title": meta["title"],
                        "full_evidence_text": doc.text,
                        "hypothesis_full_definition": hypothesis_full_definition(pair_code, side_label),
                        "categoria": ext.categoria,
                        "justificativa": ext.justificativa,
                        "trecho_evidencia": ext.trecho_evidencia,
                        "prompt_sent": ext.prompt_sent,
                        "raw_response": ext.raw_response,
                    }
                )
    return pd.DataFrame(rows)


def run_joint_condition(docs, provider) -> pd.DataFrame:
    """Condition D: one call per candidate (not per side), scoring both
    hypothesis sides at once. Returns a dataframe with the same
    pair_side_fk_id_ev key shape as extraction_rows (including the same
    full-text/full-definition/audit-trail columns), one row per side per
    candidate, so it can be compared against A/B/C's categoria column
    directly with the same reproducibility_report() machinery."""
    rows = []
    for fk_id_ev, pair_code in ASSIGNMENTS:
        d = docs[fk_id_ev]
        text = d["complete_evidence_content"]
        messages, schema = build_joint_hypothesis_messages_and_schema(pair_code, text)
        print(f"--- [joint] {pair_code} {fk_id_ev} ---", flush=True)
        t0 = time.time()
        try:
            result = provider.extract(messages, schema)
            parsed = result.parsed
            for side_label, categoria, justificativa, trecho in (
                ("a", parsed.categoria_a, parsed.justificativa_a, parsed.trecho_evidencia_a),
                ("b", parsed.categoria_b, parsed.justificativa_b, parsed.trecho_evidencia_b),
            ):
                rows.append(
                    {
                        "key": f"{pair_code}_{side_label}_{fk_id_ev}",
                        "pair": pair_code, "side": side_label, "fk_id_ev": fk_id_ev,
                        "title": d["evidence_title"],
                        "full_evidence_text": text,
                        "hypothesis_full_definition": hypothesis_full_definition(pair_code, side_label),
                        "categoria": categoria, "justificativa": justificativa,
                        "trecho_evidencia": trecho,
                        "prompt_sent": json.dumps(messages, ensure_ascii=False),
                        "raw_response": result.raw_response,
                    }
                )
        except Exception as exc:  # noqa: BLE001 -- report and continue to the next candidate
            print(f"  {fk_id_ev} raised: {exc}")
        print(f"  done in {time.time() - t0:.1f}s", flush=True)
    return pd.DataFrame(rows)


def summarize_comparison(name_a: str, df_a: pd.DataFrame, name_b: str, df_b: pd.DataFrame) -> dict:
    report = reproducibility_report(df_a[["key", "categoria"]], df_b[["key", "categoria"]], id_col="key")
    stats = report["per_column"]["categoria"]
    print(f"\n=== {name_a} vs {name_b} ===")
    print(f"exact_match_rate: {stats['exact_match_rate']:.3f}  kappa: {stats['kappa']}")
    print(f"{len(report['mismatches'])} mismatches of {len(df_a)} compared")
    return report


def main() -> None:
    with open(SCRATCH / "v7_candidates_full.json", encoding="utf-8") as f:
        docs = json.load(f)

    db_path = Path("data/v7_tuning_experiments.sqlite")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    engine = get_engine(f"sqlite:///{db_path}")
    provider = CliProvider(command=["agy", "-p"], prompt_mode="arg", timeout=300)

    with Session(engine) as session:
        codebook_ids, corpus_ids = seed_documents_and_codebooks(session, docs)
    print(f"Seeded {len(ASSIGNMENTS)} documents across {len(corpus_ids)} corpora, "
          f"{len(codebook_ids)} codebooks into {db_path}")

    run_ids_a = run_condition(engine, provider, "baseline", codebook_ids, corpus_ids, include_persona=True)
    run_ids_b = run_condition(engine, provider, "no_persona", codebook_ids, corpus_ids, include_persona=False)
    run_ids_c = run_condition(engine, provider, "repeat", codebook_ids, corpus_ids, include_persona=True)
    df_d = run_joint_condition(docs, provider)

    df_a = extraction_rows(engine, run_ids_a)
    df_b = extraction_rows(engine, run_ids_b)
    df_c = extraction_rows(engine, run_ids_c)

    reports = {
        "A_baseline_vs_B_no_persona": summarize_comparison("baseline", df_a, "no_persona", df_b),
        "A_baseline_vs_C_repeat": summarize_comparison("baseline", df_a, "repeat", df_c),
        "A_baseline_vs_D_joint": summarize_comparison("baseline (blind calls)", df_a, "joint (single call)", df_d),
    }

    combined = pd.concat(
        [
            df_a.assign(condition="A_baseline"),
            df_b.assign(condition="B_no_persona"),
            df_c.assign(condition="C_repeat"),
            df_d.assign(condition="D_joint"),
        ],
        ignore_index=True,
    )
    out_csv = Path("data/v7_tuning_experiments_results.csv")
    combined.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"\nWrote {len(combined)} rows across 4 conditions to {out_csv}")

    out_json = Path("data/v7_tuning_experiments_summary.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(
            {
                name: {
                    "exact_match_rate": r["per_column"]["categoria"]["exact_match_rate"],
                    "kappa": r["per_column"]["categoria"]["kappa"],
                    "n_mismatches": len(r["mismatches"]),
                    "mismatches": r["mismatches"],
                }
                for name, r in reports.items()
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"Wrote comparison summary to {out_json}")


if __name__ == "__main__":
    main()
