"""Post-processing-only recovery for run_v7_tuning_A_C_via_api.py.

All 64 real LLM calls already succeeded against the running backend
(port 8010) before the original script crashed in attach_metadata() with
KeyError: 'fk_id_ev' (now fixed in run_v7_tuning_A_C_via_api.py itself).
This script re-does ONLY the results-fetch + metadata-join + CSV/JSON
write, against the run_ids/corpus_ids already known from that run's log
output -- no re-seeding, no new /runs POSTs, no new LLM calls.

Usage (backend must still be running on port 8010 with the same data):
    python scripts/postprocess_v7_tuning_A_C_via_api.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import httpx  # noqa: E402
import pandas as pd  # noqa: E402

from text_as_data.validation import reproducibility_report  # noqa: E402
import run_v7_tuning_experiments as exp  # noqa: E402
from run_v7_tuning_A_C_via_api import BASE_URL, results_via_api, attach_metadata  # noqa: E402

# Fixed mapping recovered from the original run's log output (seed_via_api /
# run_via_api iterate PAIR_CODES x ("a","b") deterministically, confirmed
# line-by-line against "--- [baseline] H1 side a (run_id=1) ---" etc.).
RUN_IDS_A = {
    ("H1", "a"): 1, ("H1", "b"): 2,
    ("H2", "a"): 3, ("H2", "b"): 4,
    ("H3", "a"): 5, ("H3", "b"): 6,
}
RUN_IDS_C = {
    ("H1", "a"): 7, ("H1", "b"): 8,
    ("H2", "a"): 9, ("H2", "b"): 10,
    ("H3", "a"): 11, ("H3", "b"): 12,
}
CORPUS_IDS = {"H1": "v7_api_H1", "H2": "v7_api_H2", "H3": "v7_api_H3"}


def main() -> None:
    with open(exp.SCRATCH / "v7_candidates_full.json", encoding="utf-8") as f:
        docs = json.load(f)

    with httpx.Client(timeout=310.0) as client:
        df_a = attach_metadata(client, results_via_api(client, RUN_IDS_A), CORPUS_IDS, docs)
        df_c = attach_metadata(client, results_via_api(client, RUN_IDS_C), CORPUS_IDS, docs)

    report = reproducibility_report(df_a[["key", "categoria"]], df_c[["key", "categoria"]], id_col="key")
    stats = report["per_column"]["categoria"]
    print("\n=== [via real API] baseline vs repeat ===")
    print(f"exact_match_rate: {stats['exact_match_rate']:.3f}  kappa: {stats['kappa']}")
    print(f"{len(report['mismatches'])} mismatches of {len(df_a)} compared")

    combined = pd.concat([df_a.assign(condition="A_baseline_api"), df_c.assign(condition="C_repeat_api")], ignore_index=True)
    out_csv = Path("data/v7_tuning_A_C_via_api_results.csv")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"Wrote {len(combined)} rows to {out_csv}")

    out_json = Path("data/v7_tuning_A_C_via_api_summary.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(
            {"exact_match_rate": stats["exact_match_rate"], "kappa": stats["kappa"], "mismatches": report["mismatches"]},
            f, ensure_ascii=False, indent=2,
        )
    print(f"Wrote {out_json}")


if __name__ == "__main__":
    main()
