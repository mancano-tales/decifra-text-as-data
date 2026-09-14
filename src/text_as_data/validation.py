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


def _merge_sets(predicted: pd.DataFrame, gold: pd.DataFrame, *, id_col: str, set_col: str) -> pd.DataFrame:
    """Same preconditions as agreement_report: one gold row per id, at
    least one overlapping id. Returns one row per overlapping id with
    `pred` and `gold` frozenset columns."""
    if gold[id_col].duplicated().any():
        dupes = sorted(gold.loc[gold[id_col].duplicated(), id_col].unique().tolist())
        raise ValueError(
            f"gold has more than one row for the same {id_col!r} (e.g. {dupes[:5]}) -- "
            "multilabel_agreement_report expects exactly one gold label set per document; "
            "pre-aggregate multi-coder gold sets to a single consolidated row per document first"
        )
    p = pd.DataFrame({id_col: predicted[id_col], "pred": predicted[set_col].map(_as_label_set)})
    g = pd.DataFrame({id_col: gold[id_col], "gold": gold[set_col].map(_as_label_set)})
    merged = p.merge(g, on=id_col)
    if len(merged) == 0:
        raise ValueError(
            f"no overlapping {id_col!r} values between predicted and gold -- "
            f"predicted has {len(predicted)} rows, gold has {len(gold)} rows, but none share an id"
        )
    return merged


def _nan_to_none(value):
    return None if isinstance(value, float) and math.isnan(value) else float(value)


def _per_label_metrics(merged: pd.DataFrame, labels: list[str], *, id_col: str) -> dict:
    pred_ind = indicator_frame(merged.rename(columns={"pred": "s"}), labels, id_col=id_col, set_col="s")
    gold_ind = indicator_frame(merged.rename(columns={"gold": "s"}), labels, id_col=id_col, set_col="s")
    out = {}
    for label in labels:
        y_true, y_pred = gold_ind[label].to_numpy(), pred_ind[label].to_numpy()
        tp = int(((y_true == 1) & (y_pred == 1)).sum())
        fp = int(((y_true == 0) & (y_pred == 1)).sum())
        tn = int(((y_true == 0) & (y_pred == 0)).sum())
        precision, recall, f1, _ = precision_recall_fscore_support(
            y_true, y_pred, labels=[1], average=None, zero_division=0
        )
        if y_true.sum() == 0 and y_pred.sum() == 0:
            # Neither side ever used this label: kappa is undefined (sklearn
            # emits NaN plus a warning); report None, no warning.
            kappa = None
        else:
            kappa = _nan_to_none(cohen_kappa_score(y_true, y_pred))
        out[label] = {
            "kappa": kappa,
            "precision": float(precision[0]),
            "recall": float(recall[0]),
            "f1": float(f1[0]),
            "false_positive_rate": (fp / (fp + tn)) if (fp + tn) > 0 else None,
            "predicted_count": int(y_pred.sum()),
            "gold_count": int(y_true.sum()),
        }
    return out


def multilabel_agreement_report(
    predicted: pd.DataFrame,
    gold: pd.DataFrame,
    labels: list[str],
    *,
    id_col: str = "id",
    set_col: str = "labels",
    predicted_details: dict | None = None,
) -> dict:
    """Compare predicted label *sets* against gold label sets for one
    multi-label variable (spec §8.2-8.3).

    Two metric families ship here. Per label, the binary decomposition
    (kappa, precision/recall/F1, false-positive rate, counts) -- what every
    published multi-label evaluation reports and what the DATALUTA pilot
    computed by hand with N one-vs-rest codebooks. At the set level,
    exact-match ratio and sample-averaged Jaccard, plus the over-/under-
    coding signals that make Mercês et al.'s "Excessive Granularity Bias"
    measurable from day one: mean set sizes, their ratio, and a
    per-document breakdown into exact / over-coded / under-coded / mixed.
    Chance-corrected *set* agreement (Krippendorff's alpha with MASI,
    Gwet's AC1) is R6.1's job; this dict leaves it room.

    `labels` is the variable's full label list in codebook order: a label
    that never occurs still gets a row of zeros instead of vanishing, and
    every list in the report follows that order. `predicted_details`
    (optional) maps id -> label -> {"rationale", "evidence_span"} so each
    over-coded label in a disagreement row carries its own quote (§3.3).
    `coverage` is the caller's to fill (it knows the corpus size).
    """
    merged = _merge_sets(predicted, gold, id_col=id_col, set_col=set_col)
    return {
        "kind": "multi_label",
        "per_label": _per_label_metrics(merged, labels, id_col=id_col),
        "set_agreement": _set_agreement(merged, labels),
        "disagreements": _set_disagreements(merged, labels, id_col=id_col, predicted_details=predicted_details or {}),
    }


def _ordered(labels_present: frozenset[str], labels: list[str]) -> list[str]:
    return [label for label in labels if label in labels_present]


def _set_agreement(merged: pd.DataFrame, labels: list[str]) -> dict:
    n = len(merged)
    exact = over = under = mixed = 0
    jaccards = []
    for pred, gold in zip(merged["pred"], merged["gold"]):
        union = pred | gold
        # Jaccard(∅, ∅) = 1: both sides agree that nothing applies.
        jaccards.append(1.0 if not union else len(pred & gold) / len(union))
        if pred == gold:
            exact += 1
        elif pred > gold:
            over += 1     # pred ⊋ gold -- Mercês et al.'s "coding with expansion"
        elif pred < gold:
            under += 1    # pred ⊊ gold
        else:
            mixed += 1    # neither is a subset of the other
    mean_pred = float(merged["pred"].map(len).mean())
    mean_gold = float(merged["gold"].map(len).mean())
    return {
        "exact_match_ratio": exact / n,
        "mean_jaccard": float(sum(jaccards) / n),
        "mean_predicted_set_size": mean_pred,
        "mean_gold_set_size": mean_gold,
        "set_size_ratio": (mean_pred / mean_gold) if mean_gold > 0 else None,
        "documents": {"exact": exact, "over_coded": over, "under_coded": under, "mixed": mixed},
    }


def _set_disagreements(merged: pd.DataFrame, labels: list[str], *, id_col: str, predicted_details: dict) -> list[dict]:
    rows = []
    for _, row in merged.iterrows():
        pred, gold = row["pred"], row["gold"]
        if pred == gold:
            continue
        only_pred = _ordered(pred - gold, labels)
        only_gold = _ordered(gold - pred, labels)
        doc_details = predicted_details.get(row[id_col], {})
        rows.append(
            {
                id_col: row[id_col],
                "predicted": _ordered(pred, labels),
                "gold": _ordered(gold, labels),
                "only_predicted": only_pred,
                "only_gold": only_gold,
                # One entry per over-coded label so the reviewer can read
                # *that label's* quote (spec §3.3/§8.3); empty strings when
                # the caller had none (per_set variables, human-added labels).
                "only_predicted_details": {
                    label: {
                        "rationale": str(doc_details.get(label, {}).get("rationale", "")),
                        "evidence_span": str(doc_details.get(label, {}).get("evidence_span", "")),
                    }
                    for label in only_pred
                },
            }
        )
    rows.sort(key=lambda r: (-(len(r["only_predicted"]) + len(r["only_gold"])), r[id_col]))
    return rows
