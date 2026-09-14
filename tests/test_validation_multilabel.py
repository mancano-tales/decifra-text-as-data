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
    multilabel_reproducibility_report,
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


def test_set_level_agreement_matches_hand_computation():
    s = multilabel_agreement_report(PREDICTED, GOLD, LABELS, id_col="id", set_col="labels")["set_agreement"]
    assert s["exact_match_ratio"] == pytest.approx(2 / 6)
    assert s["mean_jaccard"] == pytest.approx(19 / 36)
    assert s["mean_predicted_set_size"] == pytest.approx(7 / 6)
    assert s["mean_gold_set_size"] == pytest.approx(7 / 6)
    assert s["set_size_ratio"] == pytest.approx(1.0)
    assert s["documents"] == {"exact": 2, "over_coded": 2, "under_coded": 1, "mixed": 1}
    assert sum(s["documents"].values()) == 6


def test_set_size_ratio_is_none_when_gold_is_all_empty():
    pred = pd.DataFrame({"id": [1, 2], "labels": [{"a"}, {"a", "b"}]})
    gold = pd.DataFrame({"id": [1, 2], "labels": [set(), set()]})
    s = multilabel_agreement_report(pred, gold, LABELS, id_col="id", set_col="labels")["set_agreement"]
    assert s["mean_gold_set_size"] == 0.0 and s["set_size_ratio"] is None
    assert s["documents"] == {"exact": 0, "over_coded": 2, "under_coded": 0, "mixed": 0}


def test_disagreements_show_the_symmetric_difference_in_codebook_order_sorted_by_size():
    report = multilabel_agreement_report(PREDICTED, GOLD, LABELS, id_col="id", set_col="labels")
    rows = report["disagreements"]
    assert [r["id"] for r in rows] == [4, 2, 3, 6]
    r4 = rows[0]
    assert r4["predicted"] == ["c"] and r4["gold"] == ["a", "b"]
    assert r4["only_predicted"] == ["c"] and r4["only_gold"] == ["a", "b"]
    r6 = rows[3]
    assert r6["predicted"] == ["a", "b", "c"]  # codebook order even though input was a set
    assert r6["only_predicted"] == ["c"] and r6["only_gold"] == []
    # Details default to an empty dict per over-coded label when none were supplied.
    assert r6["only_predicted_details"] == {"c": {"rationale": "", "evidence_span": ""}}


def test_disagreements_carry_the_per_label_quote_for_each_over_coded_label():
    details = {6: {"c": {"rationale": "mentions a court", "evidence_span": "o juiz decidiu"},
                   "a": {"rationale": "unused: a is correct", "evidence_span": "x"}},
               2: {"b": {"rationale": "b?", "evidence_span": "quote b"}}}
    report = multilabel_agreement_report(PREDICTED, GOLD, LABELS, id_col="id", set_col="labels",
                                         predicted_details=details)
    by_id = {r["id"]: r for r in report["disagreements"]}
    assert by_id[6]["only_predicted_details"] == {"c": {"rationale": "mentions a court", "evidence_span": "o juiz decidiu"}}
    assert by_id[2]["only_predicted_details"] == {"b": {"rationale": "b?", "evidence_span": "quote b"}}
    assert by_id[3]["only_predicted_details"] == {}  # under-coded: nothing over-predicted


def test_rejects_duplicate_gold_rows_and_disjoint_ids_like_agreement_report():
    dup = pd.concat([GOLD, GOLD.iloc[[0]]])
    with pytest.raises(ValueError, match="more than one row"):
        multilabel_agreement_report(PREDICTED, dup, LABELS, id_col="id", set_col="labels")
    with pytest.raises(ValueError, match="no overlapping"):
        multilabel_agreement_report(PREDICTED, GOLD.assign(id=GOLD["id"] + 100), LABELS, id_col="id", set_col="labels")


def test_predicted_ids_missing_from_gold_are_simply_not_scored():
    extra = pd.concat([PREDICTED, pd.DataFrame({"id": [99], "labels": [{"a"}]})])
    report = multilabel_agreement_report(extra, GOLD, LABELS, id_col="id", set_col="labels")
    assert sum(report["set_agreement"]["documents"].values()) == 6


def test_reproducibility_relabels_predicted_gold_as_run_a_run_b():
    report = multilabel_reproducibility_report(PREDICTED, GOLD, LABELS, id_col="id", set_col="labels")
    assert report["kind"] == "multi_label"
    assert "exact_match_ratio" in report["set_agreement"] and "mean_jaccard" in report["set_agreement"]
    # Self-agreement has no "gold"; the two runs are symmetric in name.
    assert report["set_agreement"]["mean_run_a_set_size"] == pytest.approx(7 / 6)
    assert report["set_agreement"]["mean_run_b_set_size"] == pytest.approx(7 / 6)
    assert "mean_predicted_set_size" not in report["set_agreement"]
    row = report["disagreements"][0]
    assert set(row) >= {"run_a", "run_b", "only_run_a", "only_run_b"}
    assert "predicted" not in row and "gold" not in row and "only_predicted_details" not in row
    assert report["per_label"]["a"]["run_a_count"] == 3 and report["per_label"]["a"]["run_b_count"] == 4
