import sys
from pathlib import Path

import pandas as pd
import pytest
from pydantic import BaseModel

from text_as_data import Codebook, agreement_report, extract

sys.path.insert(0, str(Path(__file__).parent.parent / "examples" / "toy_example"))


class Label(BaseModel):
    category: str


class FakeChatCompletions:
    def __init__(self, answers: dict[str, str]):
        self.answers = answers

    def create(self, model, response_model, messages):
        text = messages[-1]["content"]
        return response_model(category=self.answers[text])


class FakeClient:
    def __init__(self, answers: dict[str, str]):
        self.chat = type("Chat", (), {"completions": FakeChatCompletions(answers)})()


@pytest.fixture
def toy_codebook_module():
    import codebook as toy_module

    return toy_module


def test_extract_returns_one_row_per_text():
    texts = pd.DataFrame({"id": [1, 2], "text": ["a", "b"]})
    fake = FakeClient({"a": "x", "b": "y"})
    codebook = Codebook(schema=Label, instructions="irrelevant for this test")

    result = extract(texts, codebook, fake, model="fake-model")

    assert list(result["id"]) == [1, 2]
    assert list(result["category"]) == ["x", "y"]


def test_agreement_report_flags_mismatches():
    predicted = pd.DataFrame({"id": [1, 2, 3], "category": ["x", "y", "x"]})
    gold = pd.DataFrame({"id": [1, 2, 3], "category": ["x", "x", "x"]})

    report = agreement_report(predicted, gold)

    assert report["per_column"]["category"]["accuracy"] == pytest.approx(2 / 3)
    assert len(report["mismatches"]) == 1
    assert report["mismatches"][0]["id"] == 2


def test_agreement_report_includes_precision_recall_f1_per_category():
    predicted = pd.DataFrame(
        {"id": [1, 2, 3, 4], "category": ["protest", "protest", "not_protest", "protest"]}
    )
    gold = pd.DataFrame(
        {"id": [1, 2, 3, 4], "category": ["protest", "not_protest", "not_protest", "protest"]}
    )

    report = agreement_report(predicted, gold)

    metrics = report["per_column"]["category"]
    assert set(metrics["precision"].keys()) == {"protest", "not_protest"}
    # 3 rows predicted "protest" (1, 2, 4); 2 of those are actually gold "protest" (1, 4) -> 2/3
    assert metrics["precision"]["protest"] == pytest.approx(2 / 3)
    # 2 rows are actually gold "protest" (1, 4); both predicted correctly -> 2/2
    assert metrics["recall"]["protest"] == pytest.approx(1.0)
    assert "f1" in metrics
    assert metrics["f1"]["protest"] == pytest.approx(0.8)  # 2*P*R/(P+R) = 2*(2/3)*1/(2/3+1)


def test_agreement_report_kappa_is_json_serializable_none_not_nan_for_single_label_data():
    # Every row is the same category on both sides -- the exact "LLM always
    # predicts the majority class" case kappa exists to catch. sklearn
    # returns nan (not an error) here, and nan isn't valid JSON.
    predicted = pd.DataFrame({"id": [1, 2, 3], "category": ["protest", "protest", "protest"]})
    gold = pd.DataFrame({"id": [1, 2, 3], "category": ["protest", "protest", "protest"]})

    report = agreement_report(predicted, gold)

    kappa = report["per_column"]["category"]["kappa"]
    assert kappa is None
    import json

    # json.dumps() alone won't catch this -- Python's json module allows a
    # bare NaN token by default. Assert the serialized text is actually
    # free of it (browsers' JSON.parse() rejects a literal NaN token).
    assert "NaN" not in json.dumps(report)


def test_agreement_report_raises_a_clear_error_when_no_ids_overlap():
    # Disjoint id sets (e.g. mismatched id formats between a gold CSV and
    # the run's own document ids) merge to an empty DataFrame -- sklearn's
    # metric functions raise a cryptic "Found empty input array" ValueError
    # on that instead of a message pointing at the actual problem.
    predicted = pd.DataFrame({"id": [1, 2], "category": ["protest", "not_protest"]})
    gold = pd.DataFrame({"id": [99, 100], "category": ["protest", "not_protest"]})

    with pytest.raises(ValueError, match="no overlapping"):
        agreement_report(predicted, gold)


def test_agreement_report_raises_a_clear_error_on_duplicate_gold_ids():
    # agreement_report assumes exactly one gold row per document -- a
    # multi-coder gold set (db.py's HumanLabelRecord deliberately allows
    # more than one label per document for inter-rater work) would
    # otherwise silently fan out the merge, inflating the sample size.
    predicted = pd.DataFrame({"id": [1, 2], "category": ["protest", "not_protest"]})
    gold = pd.DataFrame({"id": [1, 1, 2], "category": ["protest", "not_protest", "not_protest"]})

    with pytest.raises(ValueError, match="more than one row"):
        agreement_report(predicted, gold)


def test_toy_example_codebook_builds_messages(toy_codebook_module):
    codebook = toy_codebook_module.toy_codebook

    messages = codebook.build_messages("Some new statement about the policy.")

    assert messages[0]["role"] == "system"
    assert "supportive" in messages[0]["content"]
    assert messages[-1]["content"] == "Some new statement about the policy."
