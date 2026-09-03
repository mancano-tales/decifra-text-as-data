"""Re-run conditions A (baseline) and C (reproducibility repeat) through
Cifra's real HTTP API (POST /codebooks, POST /corpora/documents,
POST /runs, GET /runs/{id}, GET /runs/{id}/results) instead of calling
run_extraction() directly in a script.

Why this exists: the author asked why the tuning experiments called
run_extraction() directly rather than acting like a real user of the
Cifra product. Honest answer -- conditions B (persona ablation) and D
(joint scoring) genuinely cannot go through the current API (persona
toggling isn't exposed via CreateRunRequest by design, and joint scoring
needs a schema the general Codebook class can't express), but A and C
could have: bypass_cache is already a real CreateRunRequest field. This
script closes that gap for A and C specifically -- same underlying
run_extraction() call either way, but now reached through the actual
product surface (HTTP request -> BackgroundTasks -> run_extraction),
not a Python function call in a script.

Requires the real backend running first:
    .venv/Scripts/python.exe -m uvicorn text_as_data.app:app --port 8010

Usage:
    python scripts/run_v7_tuning_A_C_via_api.py
"""

from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import httpx  # noqa: E402
import pandas as pd  # noqa: E402

from text_as_data.pilot_v7 import build_enriched_hypothesis_codebook_spec  # noqa: E402
from text_as_data.validation import reproducibility_report  # noqa: E402
import run_v7_tuning_experiments as exp  # noqa: E402

BASE_URL = "http://localhost:8010"


def seed_via_api(client: httpx.Client, docs: dict) -> tuple[dict[tuple[str, str], int], dict[str, str]]:
    """POST /codebooks and POST /corpora/documents for each pair/side --
    the same shape seed_documents_and_codebooks builds directly against
    the DB, but reached through the real endpoints this time."""
    codebook_ids: dict[tuple[str, str], int] = {}
    corpus_ids: dict[str, str] = {}

    for pair_code in exp.PAIR_CODES:
        corpus_id = f"v7_api_{pair_code}"
        corpus_ids[pair_code] = corpus_id
        files = []
        for fk_id_ev, pair in exp.ASSIGNMENTS:
            if pair != pair_code:
                continue
            text = docs[fk_id_ev]["complete_evidence_content"]
            files.append(("files", (f"{fk_id_ev}.txt", io.BytesIO(text.encode("utf-8")), "text/plain")))
        resp = client.post(f"{BASE_URL}/corpora/documents", data={"name": corpus_id}, files=files)
        resp.raise_for_status()
        print(f"POST /corpora/documents {corpus_id}: {resp.json()['document_count']} documents")

        for side_label in ("a", "b"):
            spec = build_enriched_hypothesis_codebook_spec(pair_code, side_label)
            resp = client.post(f"{BASE_URL}/codebooks", json=spec)
            resp.raise_for_status()
            codebook_ids[(pair_code, side_label)] = resp.json()["id"]

    return codebook_ids, corpus_ids


def run_via_api(client: httpx.Client, condition_name: str, codebook_ids, corpus_ids, bypass_cache: bool):
    """POST /runs for each (pair, side), then poll GET /runs/{id} until
    done -- the same sequence a real frontend does after the user clicks
    'Run'."""
    run_ids: dict[tuple[str, str], int] = {}
    for (pair_code, side_label), codebook_id in codebook_ids.items():
        resp = client.post(
            f"{BASE_URL}/runs",
            json={
                "codebook_id": codebook_id,
                "corpus_id": corpus_ids[pair_code],
                "model": f"agy-gemini-api-{condition_name}",
                "provider_mode": "cli",
                "cli_command": ["agy", "-p"],
                "cli_prompt_mode": "arg",
                "bypass_cache": bypass_cache,
            },
        )
        resp.raise_for_status()
        run_ids[(pair_code, side_label)] = resp.json()["run_id"]

    for (pair_code, side_label), run_id in run_ids.items():
        print(f"--- [{condition_name}] {pair_code} side {side_label} (run_id={run_id}) waiting ---", flush=True)
        t0 = time.time()
        while True:
            resp = client.get(f"{BASE_URL}/runs/{run_id}")
            resp.raise_for_status()
            body = resp.json()
            if body["status"] in ("done", "error"):
                break
            time.sleep(5)
        print(f"  {body['status']} in {time.time() - t0:.1f}s ({body['processed']}/{body['total']})", flush=True)

    return run_ids


def results_via_api(client: httpx.Client, run_ids: dict[tuple[str, str], int]) -> pd.DataFrame:
    rows = []
    for (pair_code, side_label), run_id in run_ids.items():
        resp = client.get(f"{BASE_URL}/runs/{run_id}/results")
        resp.raise_for_status()
        for row in resp.json():
            # /runs/{id}/results doesn't include the source doc's own
            # fk_id_ev/title metadata (it returns a snippet, not the
            # metadata_json) -- pull those separately via /corpora so this
            # output keeps the same audit-trail shape as the other
            # conditions.
            rows.append({**row, "pair": pair_code, "side": side_label})
    return pd.DataFrame(rows)


def attach_metadata(client: httpx.Client, df: pd.DataFrame, corpus_ids: dict[str, str], docs: dict) -> pd.DataFrame:
    doc_meta_by_id: dict[int, dict] = {}
    for pair_code, corpus_id in corpus_ids.items():
        resp = client.get(f"{BASE_URL}/corpora/{corpus_id}/documents", params={"limit": 100})
        resp.raise_for_status()
        for d in resp.json():
            doc_meta_by_id[d["id"]] = json.loads(d["metadata_json"])

    def row_extra(row):
        meta = doc_meta_by_id[row["document_id"]]
        # /corpora/documents (the real multi-file upload endpoint) only
        # ever stores {"filename": ...} in metadata_json -- unlike the
        # direct-DB seeding path used by the other conditions, it has no
        # fk_id_ev field. Recover it from the filename we chose at upload
        # time (f"{fk_id_ev}.txt" in seed_via_api above).
        fk_id_ev = meta["filename"].removesuffix(".txt")
        d = docs[fk_id_ev]
        return pd.Series(
            {
                "key": f"{row['pair']}_{row['side']}_{fk_id_ev}",
                "fk_id_ev": fk_id_ev,
                "title": d["evidence_title"],
                "full_evidence_text": d["complete_evidence_content"],
                "hypothesis_full_definition": exp.hypothesis_full_definition(row["pair"], row["side"]),
            }
        )

    extra = df.apply(row_extra, axis=1)
    return pd.concat([df, extra], axis=1)


def main() -> None:
    with open(exp.SCRATCH / "v7_candidates_full.json", encoding="utf-8") as f:
        docs = json.load(f)

    with httpx.Client(timeout=310.0) as client:
        codebook_ids, corpus_ids = seed_via_api(client, docs)
        print(f"Seeded via API: {len(codebook_ids)} codebooks, {len(corpus_ids)} corpora")

        run_ids_a = run_via_api(client, "baseline", codebook_ids, corpus_ids, bypass_cache=True)
        run_ids_c = run_via_api(client, "repeat", codebook_ids, corpus_ids, bypass_cache=True)

        df_a = attach_metadata(client, results_via_api(client, run_ids_a), corpus_ids, docs)
        df_c = attach_metadata(client, results_via_api(client, run_ids_c), corpus_ids, docs)

    report = reproducibility_report(df_a[["key", "categoria"]], df_c[["key", "categoria"]], id_col="key")
    stats = report["per_column"]["categoria"]
    print(f"\n=== [via real API] baseline vs repeat ===")
    print(f"exact_match_rate: {stats['exact_match_rate']:.3f}  kappa: {stats['kappa']}")
    print(f"{len(report['mismatches'])} mismatches of {len(df_a)} compared")

    combined = pd.concat([df_a.assign(condition="A_baseline_api"), df_c.assign(condition="C_repeat_api")], ignore_index=True)
    out_csv = Path("data/v7_tuning_A_C_via_api_results.csv")
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
