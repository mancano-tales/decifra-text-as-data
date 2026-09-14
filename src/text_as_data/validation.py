from __future__ import annotations

import math

import pandas as pd
from sklearn.metrics import accuracy_score, cohen_kappa_score, precision_recall_fscore_support


def agreement_report(
    predicted: pd.DataFrame,
    gold: pd.DataFrame,
    id_col: str = "id",
    columns: list[str] | None = None,
) -> dict:
    """Compare LLM output against human-coded gold labels, column by column.

    Returns per-column accuracy, Cohen's kappa (chance-corrected -- a
    column where the LLM always predicts the majority class scores high on
    accuracy but low on kappa, which is exactly the failure mode worth
    catching before trusting the pipeline's output), precision/recall/F1
    per category label, and the list of mismatched rows for manual
    inspection.
    """
    if gold[id_col].duplicated().any():
        # agreement_report assumes exactly one gold row per document -- a
        # multi-coder gold set (more than one human label per document,
        # which db.py's HumanLabelRecord deliberately allows for
        # inter-rater work) would otherwise silently fan out the merge
        # below, duplicating each predicted row once per extra coder and
        # inflating the effective sample size. The default QualiLab import
        # path ("final" layer) already enforces this precondition before
        # writing HumanLabelRecord rows, but agreement_report shouldn't
        # rely on every caller remembering that.
        dupes = sorted(gold.loc[gold[id_col].duplicated(), id_col].unique().tolist())
        raise ValueError(
            f"gold has more than one row for the same {id_col!r} (e.g. {dupes[:5]}) -- "
            "agreement_report expects exactly one gold label per document; pre-aggregate "
            "multi-coder gold sets to a single consolidated row per document first"
        )

    merged = predicted.merge(gold, on=id_col, suffixes=("_pred", "_gold"))
    if len(merged) == 0:
        raise ValueError(
            f"no overlapping {id_col!r} values between predicted and gold -- "
            f"predicted has {len(predicted)} rows, gold has {len(gold)} rows, but none share an id"
        )
    if columns is None:
        columns = [c for c in gold.columns if c != id_col]

    per_column = {}
    mismatches = []
    for col in columns:
        pred_col, gold_col = f"{col}_pred", f"{col}_gold"
        labels = sorted(set(merged[gold_col]) | set(merged[pred_col]))
        precision, recall, f1, _ = precision_recall_fscore_support(
            merged[gold_col], merged[pred_col], labels=labels, average=None, zero_division=0
        )
        kappa = cohen_kappa_score(merged[gold_col], merged[pred_col])
        if isinstance(kappa, float) and math.isnan(kappa):
            # sklearn returns nan (not an error) when there's only one label
            # in common between predicted and gold -- the exact "LLM always
            # predicts the majority class" case kappa exists to catch, so
            # this is an expected input, not a bug to raise on. `nan` isn't
            # valid JSON (json.dumps emits a bare `NaN` token that
            # JSON.parse() rejects), so it's reported as `None` instead.
            kappa = None
        per_column[col] = {
            "accuracy": accuracy_score(merged[gold_col], merged[pred_col]),
            "kappa": kappa,
            "precision": dict(zip(labels, precision)),
            "recall": dict(zip(labels, recall)),
            "f1": dict(zip(labels, f1)),
        }
        disagreements = merged[merged[pred_col] != merged[gold_col]]
        for _, row in disagreements.iterrows():
            mismatches.append(
                {
                    id_col: row[id_col],
                    "column": col,
                    "predicted": row[pred_col],
                    "gold": row[gold_col],
                }
            )

    return {"per_column": per_column, "mismatches": mismatches}


def reproducibility_report(
    run_a: pd.DataFrame,
    run_b: pd.DataFrame,
    id_col: str = "document_id",
    columns: list[str] | None = None,
) -> dict:
    """Compare two runs of the *same* codebook+model+corpus against each
    other, to measure whether the pipeline's own output is stable -- not
    whether it's correct (there is no gold label here, just two answers to
    the same question).

    A thin relabeling of `agreement_report()`: the statistics for "does A
    match B" are identical whether B is a human gold label or a second LLM
    run, so this reuses that function's merge/accuracy/kappa/precision/
    recall/mismatch logic rather than re-implementing it, and only renames
    the "predicted"/"gold" keys to the more accurate "run_a"/"run_b" for a
    comparison where neither side is the ground truth.
    """
    result = agreement_report(run_a, run_b, id_col=id_col, columns=columns)
    for stats in result["per_column"].values():
        stats["exact_match_rate"] = stats.pop("accuracy")
    for mismatch in result["mismatches"]:
        mismatch["run_a"] = mismatch.pop("predicted")
        mismatch["run_b"] = mismatch.pop("gold")
    return result


def _as_label_set(value) -> frozenset[str]:
    """Normalize a cell holding a set of labels. Accepts set/frozenset/
    list/tuple (lists may carry duplicates -- a model repeating a label is
    not a wrong answer, spec §3.2). None/NaN means the empty set."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return frozenset()
    if isinstance(value, str):
        # A bare string is almost certainly a caller bug (one label passed
        # where a set was expected); refuse rather than iterate its characters.
        raise TypeError(f"expected a set of labels, got the string {value!r}")
    return frozenset(value)


def indicator_frame(frame: pd.DataFrame, labels: list[str], *, id_col: str, set_col: str) -> pd.DataFrame:
    """One 0/1 column per label (codebook order), plus `id_col`. This is the
    binary decomposition every per-label metric is computed on, kept public
    because R6.6's PPI prevalence estimator needs exactly these vectors."""
    known = set(labels)
    rows = []
    for _, row in frame.iterrows():
        present = _as_label_set(row[set_col])
        unknown = present - known
        if unknown:
            raise ValueError(
                f"{id_col}={row[id_col]!r}: labels {sorted(unknown)} are not in the label list {labels}"
            )
        rows.append({id_col: row[id_col], **{label: int(label in present) for label in labels}})
    return pd.DataFrame(rows, columns=[id_col, *labels]).astype({label: "int64" for label in labels})
