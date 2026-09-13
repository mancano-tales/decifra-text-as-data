"""Run the 16 candidate V7 evidence/hypothesis-pair evaluations through the
real Decifra pipeline (codebook -> DB -> run_extraction -> CliProvider),
using Google Antigravity's `agy` CLI instead of Claude.

This replaces the earlier hand-drafted classifications (data/
v7_pilot_draft_classifications.csv) with actual LLM output from the real
extraction engine -- the point being to exercise Decifra itself, not to have
an agent eyeball each article and write down a guess.

Usage:
    python scripts/run_v7_candidates_via_agy.py
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlmodel import Session, select  # noqa: E402

from text_as_data.codebook import spec_to_yaml_string  # noqa: E402
from text_as_data.db import CodebookRecord, DocumentRecord, ExtractionRecord, RunRecord, get_engine  # noqa: E402
from text_as_data.extraction import run_extraction  # noqa: E402
from text_as_data.pilot_v7 import HYPOTHESIS_DEFINITIONS, build_enriched_hypothesis_codebook_spec  # noqa: E402
from text_as_data.providers import CliProvider  # noqa: E402

SCRATCH = Path(
    "C:/Users/Mancano/AppData/Local/Temp/claude/"
    "C--Users-Mancano-Documents-MancanoSync-text-as-data/"
    "64bf4a45-2f26-4117-8f92-ab0c1cf78c1f/scratchpad"
)

# (fk_id_ev, hypothesis_pair)
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


def write_codebook_yaml(pair_code: str, side_label: str) -> str:
    """Enriched codebook (full mechanism/premises + boundary_notes), not the
    bare-bones name-only version this pilot originally used -- see
    pilot_v7.build_enriched_hypothesis_codebook_spec's docstring for why."""
    return spec_to_yaml_string(build_enriched_hypothesis_codebook_spec(pair_code, side_label))


def main() -> None:
    with open(SCRATCH / "v7_candidates_full.json", encoding="utf-8") as f:
        docs = json.load(f)

    db_path = Path("data/v7_candidates_enriched.sqlite")
    if db_path.exists():
        db_path.unlink()
    engine = get_engine(f"sqlite:///{db_path}")

    provider = CliProvider(command=["agy", "-p"], prompt_mode="arg", timeout=300)

    run_ids_by_pair_side: dict[tuple[str, str], int] = {}
    pair_codes = sorted({pair for _, pair in ASSIGNMENTS})

    with Session(engine) as session:
        for pair_code in pair_codes:
            corpus_id = f"v7_candidates_{pair_code}"
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
                session.flush()

            for side_label in ("a", "b"):
                yaml_raw = write_codebook_yaml(pair_code, side_label)
                codebook = CodebookRecord(name=f"{pair_code}_{side_label}", yaml_raw=yaml_raw)
                session.add(codebook)
                session.flush()

                run = RunRecord(codebook_id=codebook.id, corpus_id=corpus_id, model="agy-gemini")
                session.add(run)
                session.flush()
                run_ids_by_pair_side[(pair_code, side_label)] = run.id

        session.commit()

    print(f"Seeded {len(ASSIGNMENTS)} documents and {len(run_ids_by_pair_side)} runs into {db_path}")

    for (pair_code, side_label), run_id in run_ids_by_pair_side.items():
        print(f"--- running {pair_code} side {side_label} (run_id={run_id}) ---", flush=True)
        t0 = time.time()
        try:
            run_extraction(engine, run_id, provider)
        except Exception as exc:  # noqa: BLE001 -- report and continue to the next run
            print(f"  run {run_id} raised: {exc}")
        print(f"  done in {time.time() - t0:.1f}s", flush=True)

    # Every spreadsheet output from this pilot must carry the complete
    # hypothesis definition and the complete evidence text sent to the LLM
    # -- not just labels/IDs -- so a human reviewer never has to hunt down
    # source material to check a row (author's explicit requirement,
    # 2026-09-01, after the first draft CSV only had a short justificativa).
    with Session(engine) as session:
        rows = []
        for (pair_code, side_label), run_id in run_ids_by_pair_side.items():
            other_label = "b" if side_label == "a" else "a"
            pair_def = HYPOTHESIS_DEFINITIONS[pair_code]
            this_hyp = pair_def[side_label]
            other_hyp = pair_def[other_label]
            hypothesis_full_definition = (
                f"{this_hyp['name']}\n"
                f"Mechanism: {this_hyp['mechanism']}\n"
                f"Premises: {this_hyp['premises']}\n\n"
                f"Rival hypothesis in this pair: {other_hyp['name']}\n"
                f"Rival mechanism: {other_hyp['mechanism']}"
            )

            extractions = session.exec(select(ExtractionRecord).where(ExtractionRecord.run_id == run_id)).all()
            for ext in extractions:
                doc = session.get(DocumentRecord, ext.document_id)
                meta = json.loads(doc.metadata_json)
                rows.append(
                    {
                        "fk_id_ev": meta["fk_id_ev"],
                        "title": meta["title"],
                        "full_evidence_text": doc.text,
                        "hypothesis_pair": pair_code,
                        "side": side_label,
                        "hypothesis_full_definition": hypothesis_full_definition,
                        "agy_categoria": ext.category,
                        "agy_justificativa": ext.rationale,
                        "agy_trecho_evidencia": ext.evidence_span,
                        # Audit trail: the exact prompt sent and the raw
                        # (pre-parsing) CLI output received, straight from
                        # ExtractionRecord -- so this spreadsheet is
                        # verifiable without trusting a reconstruction.
                        "prompt_sent": ext.prompt_sent,
                        "raw_response": ext.raw_response,
                    }
                )

    out_path = Path("data/v7_candidates_agy_results_enriched.csv")
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "fk_id_ev",
                "title",
                "full_evidence_text",
                "hypothesis_pair",
                "side",
                "hypothesis_full_definition",
                "agy_categoria",
                "agy_justificativa",
                "agy_trecho_evidencia",
                "prompt_sent",
                "raw_response",
            ],
        )
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} results to {out_path}")


if __name__ == "__main__":
    main()
