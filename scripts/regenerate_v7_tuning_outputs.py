"""One-off: regenerate data/v7_tuning_experiments_results.csv +
_summary.json with the full audit-trail columns (full evidence text,
full hypothesis definition, trecho_evidencia, prompt_sent, raw_response)
that the first version of run_v7_tuning_experiments.py's output
functions omitted -- see the fix to extraction_rows()/run_joint_condition()
in that file.

Reuses conditions A/B/C from the existing data/v7_tuning_experiments.sqlite
(no new LLM calls -- that data, including trecho_evidencia/prompt_sent/
raw_response, was already persisted correctly by run_extraction the first
time; only the CSV-writing step dropped it). Only condition D (joint
scoring) is re-run for real: its per-side trecho_evidencia and raw
response were never persisted anywhere the first time, so that data is
genuinely gone and the only way to recover it is 16 fresh calls.

Usage:
    python scripts/regenerate_v7_tuning_outputs.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from text_as_data.db import CodebookRecord, RunRecord, get_engine  # noqa: E402
from text_as_data.providers import CliProvider  # noqa: E402
import run_v7_tuning_experiments as exp  # noqa: E402


def recover_run_ids(engine, condition_model: str) -> dict[tuple[str, str], int]:
    """Re-derive {(pair, side): run_id} for a condition already seeded/run
    in a prior invocation, by joining RunRecord.model back to the
    codebook's own "{pair}_{side}" name -- the same naming
    seed_documents_and_codebooks already uses."""
    run_ids = {}
    with Session(engine) as session:
        runs = session.exec(select(RunRecord).where(RunRecord.model == condition_model)).all()
        for run in runs:
            codebook = session.get(CodebookRecord, run.codebook_id)
            pair_code, side_label = codebook.name.rsplit("_", 1)
            run_ids[(pair_code, side_label)] = run.id
    return run_ids


def main() -> None:
    with open(exp.SCRATCH / "v7_candidates_full.json", encoding="utf-8") as f:
        docs = json.load(f)

    db_path = Path("data/v7_tuning_experiments.sqlite")
    engine = get_engine(f"sqlite:///{db_path}")

    run_ids_a = recover_run_ids(engine, "agy-gemini-baseline")
    run_ids_b = recover_run_ids(engine, "agy-gemini-no_persona")
    run_ids_c = recover_run_ids(engine, "agy-gemini-repeat")
    print(f"Recovered run ids: A={len(run_ids_a)} B={len(run_ids_b)} C={len(run_ids_c)} (expect 6 each)")

    df_a = exp.extraction_rows(engine, run_ids_a)
    df_b = exp.extraction_rows(engine, run_ids_b)
    df_c = exp.extraction_rows(engine, run_ids_c)
    print(f"Recovered rows from existing DB (no new LLM calls): A={len(df_a)} B={len(df_b)} C={len(df_c)}")

    provider = CliProvider(command=["agy", "-p"], prompt_mode="arg", timeout=300)
    print("Re-running condition D (joint scoring) for real -- 16 calls, "
          "its per-row audit trail was never persisted the first time.")
    df_d = exp.run_joint_condition(docs, provider)
    # Checkpoint immediately -- these are real, just-paid-for LLM calls;
    # a downstream write failure (e.g. the final CSV being open in Excel,
    # which is exactly what happened the first time this script ran) must
    # not throw this data away. This filename is new, so it can't be
    # locked by whatever has the *previous* output file open.
    checkpoint_path = Path("data/v7_tuning_experiments_D_joint_checkpoint.csv")
    df_d.to_csv(checkpoint_path, index=False, encoding="utf-8-sig")
    print(f"Checkpointed condition D ({len(df_d)} rows) to {checkpoint_path}")

    reports = {
        "A_baseline_vs_B_no_persona": exp.summarize_comparison("baseline", df_a, "no_persona", df_b),
        "A_baseline_vs_C_repeat": exp.summarize_comparison("baseline", df_a, "repeat", df_c),
        "A_baseline_vs_D_joint": exp.summarize_comparison("baseline (blind calls)", df_a, "joint (single call)", df_d),
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
    # A new filename, not the original -- the original crashed this script
    # once already because it was open in Excel (PermissionError), and
    # there is no guarantee it has been closed since.
    out_csv = Path("data/v7_tuning_experiments_results_v2.csv")
    combined.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"\nWrote {len(combined)} rows (with full audit trail) to {out_csv}")

    out_json = Path("data/v7_tuning_experiments_summary_v2.json")
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
