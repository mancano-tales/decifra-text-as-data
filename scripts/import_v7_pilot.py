"""Import the 2 usable V7 pilot rows (see docs/superpowers/plans/2026-08-31-slice-1-backend-skeleton.md)
into the Decifra SQLite DB, and write the 4 per-hypothesis-side codebook
YAML files plus a gold-labels CSV for later comparison.

Re-running this script is safe: `corpus_id` (e.g. "v7_pilot_H1") is a
*shared* grouping key across all evidence rows hand-coded under the same
hypothesis pair, so it is deliberately NOT unique per document -- a Run
(Task 8/9) filters documents by `corpus_id` to process a whole pair's
evidence as a batch. Idempotency dedupes instead on the pair
(`corpus_id`, `fk_id_ev`) via `DocumentRecord.metadata_json`, so re-running
after a new evidence row has been hand-coded under an already-seen pair
still imports the new row, while a truly-already-seen (corpus_id,
fk_id_ev) pair is skipped and reported. This does NOT pick up changes to
already-seeded rows -- delete `decifra.sqlite` first to fully reseed from
scratch.

Usage:
    python scripts/import_v7_pilot.py /path/to/v7_banco_process_tracing_baesiano_abdutivo_manual.xlsx
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import openpyxl
import yaml
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from text_as_data.db import CodebookRecord, DocumentRecord, get_engine
from text_as_data.pilot_v7 import (
    VERBAL_PROBABILITY_DEFINITIONS,
    VERBAL_PROBABILITY_LABELS,
    build_hypothesis_lookup,
    fix_mojibake,
    select_gold_rows,
)


def _sheet_rows(ws) -> list[dict]:
    """Read a sheet using its own row-1 header as keys — do NOT hardcode a
    column list/order here. The workbook's `codebook` sheet documents a
    strict snake_case-in-English column-naming convention (§6 of
    `readme_v7_banco_process_tracing.md`), but does not guarantee column
    *order* matches the convention's own narrative tables, and this script
    was written from reading `tb3`/`tb4` directly, not `tb1` (see the
    plan's self-review note) — header-based reading removes that risk for
    all three sheets."""
    rows_iter = ws.iter_rows(values_only=True)
    header = next(rows_iter)
    rows = []
    for values in rows_iter:
        row = dict(zip(header, values))
        if row.get(header[0]) is None:
            continue
        rows.append(row)
    return rows


def _get_or_create_codebook(
    session: Session, pair_code: str, side_label: str, hypothesis_name: str, other_side_name: str
) -> CodebookRecord:
    """Reuse an existing codebook for this (pair_code, side_label) if one was
    already seeded -- either earlier in this same import run (a second
    evidence row hand-coded under a pair already seen this run) or in a
    prior run of this script. Without this, every kept evidence row would
    create its own duplicate `CodebookRecord` with the same name/YAML."""
    name = f"{pair_code}_{side_label}"
    existing = session.exec(select(CodebookRecord).where(CodebookRecord.name == name)).first()
    if existing is not None:
        return existing

    yaml_path = write_codebook_yaml(pair_code, side_label, hypothesis_name, other_side_name)
    codebook_record = CodebookRecord(name=name, yaml_raw=Path(yaml_path).read_text(encoding="utf-8"))
    session.add(codebook_record)
    session.flush()  # assign codebook_record.id without ending the transaction
    return codebook_record


def write_codebook_yaml(pair_code: str, side_label: str, hypothesis_name: str, other_side_name: str) -> str:
    categories = [
        {
            "label": label,
            "definition": VERBAL_PROBABILITY_DEFINITIONS[label],
        }
        for label in VERBAL_PROBABILITY_LABELS
    ]
    spec = {
        "concept": f"{pair_code}_{side_label}_probability",
        "description": (
            f"Inhabit the world of the hypothesis '{hypothesis_name}' and ask: if this "
            "hypothesis were true, how expected would this evidence be? (Fairfield & "
            f"Charman 2022.) The competing hypothesis in this pair is '{other_side_name}' "
            "-- do not evaluate that one here, only the probability of the evidence under "
            f"'{hypothesis_name}'."
        ),
        "categories": categories,
    }
    path = Path("codebooks") / f"{pair_code.lower()}_{side_label}.yaml"
    path.parent.mkdir(exist_ok=True)
    path.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return str(path)


def main(xlsx_path: str) -> None:
    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    tb1_rows = _sheet_rows(wb["tb1_hypotheses"])
    tb3_rows = {r["pk_id_ev"]: r for r in _sheet_rows(wb["tb3_evidence_raw"])}
    tb4_rows = _sheet_rows(wb["tb4_evidence_analisys"])

    required_tb1_columns = {"pk_hyp__code", "hypothesis_name", "hypothesis_group_id"}
    if tb1_rows and not required_tb1_columns.issubset(tb1_rows[0]):
        raise KeyError(
            f"tb1_hypotheses is missing expected columns {required_tb1_columns - tb1_rows[0].keys()}; "
            f"actual columns: {sorted(tb1_rows[0].keys())}. This script's tb1 column names were taken from "
            "readme_v7_banco_process_tracing.md's documentation table, not verified directly against the "
            "sheet the way tb3/tb4 were (see the plan's self-review note) -- update build_hypothesis_lookup's "
            "expected keys in pilot_v7.py to match the real names printed above."
        )

    lookup = build_hypothesis_lookup(tb1_rows)
    kept, skipped = select_gold_rows(tb4_rows, lookup)

    print(f"Resolvable + fully coded rows kept: {len(kept)}")
    print(f"Skipped (unresolvable group or incomplete): {len(skipped)}")
    for row in skipped:
        print(f"  skipped {row['fk_id_ev']!r}: group={row.get('fk_hypothesis_group')!r}")

    engine = get_engine("sqlite:///decifra.sqlite")
    gold_rows = []

    with Session(engine) as session:
        for row in kept:
            pair_code = row["fk_hypothesis_group"]

            if row["fk_id_ev"] not in tb3_rows:
                print(f"  skipping {row.get('pk_id_ev_an')!r}: fk_id_ev={row['fk_id_ev']!r} not found in tb3_evidence_raw")
                continue

            corpus_id = f"v7_pilot_{pair_code}"
            evidence_metadata = json.dumps({"fk_id_ev": row["fk_id_ev"]})
            existing_docs = session.exec(
                select(DocumentRecord).where(DocumentRecord.corpus_id == corpus_id)
            ).all()
            existing_doc = next((d for d in existing_docs if d.metadata_json == evidence_metadata), None)
            if existing_doc is not None:
                print(
                    f"  skipping seed for {pair_code} evidence {row['fk_id_ev']!r}: already present "
                    f"in decifra.sqlite (document id {existing_doc.id}) — delete decifra.sqlite first "
                    "to reseed from scratch"
                )
                continue

            side_a_name, side_b_name = lookup[pair_code]
            evidence = tb3_rows[row["fk_id_ev"]]
            text = fix_mojibake(evidence["complete_evidence_content"])

            document = DocumentRecord(corpus_id=corpus_id, text=text, metadata_json=evidence_metadata)
            session.add(document)
            session.flush()  # assign document.id without ending the transaction

            for side_label, side_name, other_name, gold_category in (
                ("a", side_a_name, side_b_name, row["prob_e_dado_h1"]),
                ("b", side_b_name, side_a_name, row["prob_e_dado_h2"]),
            ):
                codebook_record = _get_or_create_codebook(session, pair_code, side_label, side_name, other_name)

                gold_rows.append(
                    {
                        "document_id": document.id,
                        "codebook_id": codebook_record.id,
                        "codebook_name": codebook_record.name,
                        "gold_category": gold_category,
                        "gold_justificativa": fix_mojibake(row.get("ek_justificativa_likelihoods") or ""),
                    }
                )

            # Commit the document and every codebook/gold entry created for
            # it as one unit -- a failure partway through no longer leaves a
            # committed document with missing dependent records that a
            # later rerun would skip via the idempotency check above.
            session.commit()

    if not gold_rows:
        print("No gold rows produced — nothing to write.")
        return

    gold_path = Path("data") / "v7_pilot_gold.csv"
    gold_path.parent.mkdir(exist_ok=True)
    with open(gold_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(gold_rows[0].keys()))
        writer.writeheader()
        writer.writerows(gold_rows)

    print(f"Wrote {len(gold_rows)} gold rows to {gold_path}")
    print(f"Documents + codebooks seeded into decifra.sqlite")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/import_v7_pilot.py /path/to/v7_....xlsx")
    main(sys.argv[1])
