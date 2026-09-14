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
