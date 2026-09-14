"""Hand-checkable tests for the multi-label agreement report (R1.1 step 4,
spec §8.2-8.4). The six-document example below is small enough that every
reported number is derivable on paper; the expected values in each test
were computed by hand *before* the implementation, not copied from its
output."""

import math

import pandas as pd
import pytest

from text_as_data.validation import (
    indicator_frame,
    multilabel_agreement_report,
)

LABELS = ["a", "b", "c"]

# id : predicted set        gold set          relation
#  1 : {a}                  {a}               exact
#  2 : {a, b}               {a}               over-coded (pred ⊋ gold)
#  3 : {}                   {b}               under-coded (pred ⊊ gold)
#  4 : {c}                  {a, b}            mixed (neither subset)
#  5 : {}                   {}                exact (∅ vs ∅)
#  6 : {a, b, c}            {a, b}            over-coded
PREDICTED = pd.DataFrame(
    {"id": [1, 2, 3, 4, 5, 6],
     "labels": [{"a"}, {"a", "b"}, set(), {"c"}, set(), {"a", "b", "c"}]}
)
GOLD = pd.DataFrame(
    {"id": [1, 2, 3, 4, 5, 6],
     "labels": [{"a"}, {"a"}, {"b"}, {"a", "b"}, set(), {"a", "b"}]}
)


def test_indicator_frame_is_one_column_per_label_in_codebook_order():
    ind = indicator_frame(PREDICTED, LABELS, id_col="id", set_col="labels")
    assert list(ind.columns) == ["id", "a", "b", "c"]
    assert ind.set_index("id").loc[2].tolist() == [1, 1, 0]
    assert ind.set_index("id").loc[5].tolist() == [0, 0, 0]
    assert ind["a"].dtype.kind in "iu"  # integer 0/1, not bool, so sums are counts


def test_indicator_frame_accepts_lists_tuples_and_frozensets_and_ignores_unknown_labels_loudly():
    df = pd.DataFrame({"id": [1, 2, 3], "labels": [["a", "a"], ("b",), frozenset({"c"})]})
    ind = indicator_frame(df, LABELS, id_col="id", set_col="labels")
    assert ind.set_index("id").loc[1].tolist() == [1, 0, 0]  # duplicate collapses
    with pytest.raises(ValueError, match="not in the label list"):
        indicator_frame(pd.DataFrame({"id": [1], "labels": [{"zzz"}]}), LABELS, id_col="id", set_col="labels")


def test_per_label_binary_metrics_match_hand_computation():
    report = multilabel_agreement_report(PREDICTED, GOLD, LABELS, id_col="id", set_col="labels")
    assert report["kind"] == "multi_label"
    assert list(report["per_label"]) == LABELS  # codebook order, not alphabetical

    a = report["per_label"]["a"]
    assert a["predicted_count"] == 3 and a["gold_count"] == 4
    assert a["precision"] == pytest.approx(1.0)
    assert a["recall"] == pytest.approx(0.75)
    assert a["f1"] == pytest.approx(6 / 7)
    assert a["false_positive_rate"] == pytest.approx(0.0)
    assert a["kappa"] == pytest.approx(2 / 3)

    b = report["per_label"]["b"]
    assert b["predicted_count"] == 2 and b["gold_count"] == 3
    assert b["precision"] == pytest.approx(0.5)
    assert b["recall"] == pytest.approx(1 / 3)
    assert b["f1"] == pytest.approx(0.4)
    assert b["false_positive_rate"] == pytest.approx(1 / 3)
    assert b["kappa"] == pytest.approx(0.0)

    c = report["per_label"]["c"]
    assert c["predicted_count"] == 2 and c["gold_count"] == 0
    assert c["precision"] == 0.0 and c["recall"] == 0.0 and c["f1"] == 0.0
    assert c["false_positive_rate"] == pytest.approx(1 / 3)
    # Gold never contains c: kappa is degenerate. sklearn yields 0.0 here
    # (po == pe); a NaN on some version must surface as None, never as NaN.
    assert c["kappa"] is None or c["kappa"] == pytest.approx(0.0)


def test_a_label_that_never_occurs_anywhere_still_gets_a_row_of_zeros():
    report = multilabel_agreement_report(PREDICTED, GOLD, [*LABELS, "never"], id_col="id", set_col="labels")
    never = report["per_label"]["never"]
    assert never == {"kappa": None, "precision": 0.0, "recall": 0.0, "f1": 0.0,
                     "false_positive_rate": 0.0, "predicted_count": 0, "gold_count": 0}


def test_false_positive_rate_is_none_when_there_are_no_negatives():
    # Every document is gold-positive for `a`: FP + TN == 0.
    pred = pd.DataFrame({"id": [1, 2], "labels": [{"a"}, set()]})
    gold = pd.DataFrame({"id": [1, 2], "labels": [{"a"}, {"a"}]})
    report = multilabel_agreement_report(pred, gold, ["a"], id_col="id", set_col="labels")
    assert report["per_label"]["a"]["false_positive_rate"] is None


def test_no_nan_anywhere_in_the_report():
    report = multilabel_agreement_report(PREDICTED, GOLD, LABELS, id_col="id", set_col="labels")

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, float):
            assert not math.isnan(x), "NaN is not valid JSON; report None instead"

    walk(report)
