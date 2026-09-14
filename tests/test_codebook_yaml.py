import re

import pytest
import yaml

from text_as_data import Codebook
from text_as_data.codebook import spec_from_yaml_string, spec_to_yaml_string, validate_spec

YAML_SOURCE = """
concept: protest
description: >
  A collective, public event expressing a political or social claim,
  involving at least two people.
categories:
  - label: protest
    definition: >
      An occupation, march, or strike with a declared political demand.
    positive_examples:
      - "About 200 people occupied the square in front of city hall."
    negative_examples:
      - "People gathered for a cultural event with no political claim."
    boundary_notes: >
      Does not include purely ceremonial events with no claim being made.
  - label: not_protest
    definition: "Any event that does not meet the criteria above."
"""


def test_from_yaml_string_builds_schema_with_category_enum():
    codebook = Codebook.from_yaml_string(YAML_SOURCE)

    fields = codebook.schema.model_fields
    assert set(fields) == {"category", "rationale", "evidence_span"}
    assert set(fields["category"].annotation.__args__) == {"protest", "not_protest"}


def test_from_yaml_string_instructions_include_definitions_and_boundary_notes():
    codebook = Codebook.from_yaml_string(YAML_SOURCE)

    assert "occupation, march, or strike" in codebook.instructions
    assert "Does not include purely ceremonial events" in codebook.instructions


def test_build_messages_includes_persona_by_default():
    codebook = Codebook.from_yaml_string(YAML_SOURCE)

    messages = codebook.build_messages("some evidence text")

    assert "careful annotator applying a fixed coding scheme" in messages[0]["content"]
    assert codebook.instructions in messages[0]["content"]


def test_build_messages_omits_persona_when_disabled():
    # Ablation support: docs/research/2026-09-02_llm_pipeline_verification_methodology.md
    # flagged the fixed persona line as never having been measured with vs.
    # without -- this is what lets an experiment isolate its effect.
    codebook = Codebook.from_yaml_string(YAML_SOURCE)

    messages = codebook.build_messages("some evidence text", include_persona=False)

    assert "careful annotator" not in messages[0]["content"]
    assert messages[0]["content"] == codebook.instructions


def test_from_yaml_string_rejects_duplicate_labels():
    bad_yaml = YAML_SOURCE.replace("not_protest", "protest")
    with pytest.raises(ValueError, match="duplicate category label"):
        Codebook.from_yaml_string(bad_yaml)


def test_from_yaml_string_does_not_coerce_yes_no_labels_to_bool():
    yaml_with_bool_like_labels = """
concept: turnout
description: Whether the respondent says they will vote.
categories:
  - label: yes
    definition: The respondent affirms they will vote.
  - label: no
    definition: The respondent denies they will vote.
"""
    codebook = Codebook.from_yaml_string(yaml_with_bool_like_labels)

    fields = codebook.schema.model_fields
    assert set(fields["category"].annotation.__args__) == {"yes", "no"}

    instance = codebook.schema(category="yes", rationale="said so", evidence_span="\"yes\"")
    assert instance.category == "yes"


def test_from_yaml_string_rejects_empty_categories():
    empty_categories_yaml = """
concept: protest
description: A collective, public event.
categories: []
"""
    with pytest.raises(ValueError, match="at least one category"):
        Codebook.from_yaml_string(empty_categories_yaml)


def test_from_yaml_string_reports_missing_required_field_as_value_error():
    missing_concept_yaml = """
description: A collective, public event.
categories:
  - label: protest
    definition: An occupation, march, or strike.
"""
    with pytest.raises(ValueError, match="missing required field"):
        Codebook.from_yaml_string(missing_concept_yaml)


def test_from_yaml_string_rejects_a_comments_only_document_as_value_error():
    # yaml.load('# just a comment') parses to None, not a dict -- without
    # a type check, validate_spec(None) raises a raw AttributeError instead
    # of the ValueError every other invalid input in this module produces.
    comments_only_yaml = "# just a comment, no actual codebook content\n"

    with pytest.raises(ValueError, match="must be a YAML mapping"):
        Codebook.from_yaml_string(comments_only_yaml)


def test_from_yaml_string_rejects_a_non_string_label():
    # An unquoted YAML integer label (e.g. `label: 0`) is falsy under a
    # bare truthiness check (`not 0` is True) and would otherwise be
    # rejected with the same message as a genuinely missing label.
    integer_label_yaml = """
concept: protest
description: A collective, public event.
categories:
  - label: 0
    definition: An occupation, march, or strike.
  - label: not_protest
    definition: Any event that does not meet the criteria above.
"""

    with pytest.raises(ValueError, match="non-empty string"):
        Codebook.from_yaml_string(integer_label_yaml)


def test_from_yaml_string_rejects_a_category_that_is_not_a_mapping():
    # `categories: ["protest", "not_protest"]` (bare strings, not YAML
    # mappings) is truthy at the top level, so it passes the
    # `spec.get("categories")` check -- without a per-item type check,
    # `category.get("label")` then raises a raw AttributeError.
    bare_string_categories_yaml = """
concept: protest
description: A collective, public event.
categories:
  - protest
  - not_protest
"""

    with pytest.raises(ValueError, match="must be a YAML mapping"):
        Codebook.from_yaml_string(bare_string_categories_yaml)


VALID_SPEC = {
    "concept": "protest",
    "description": "A collective, public event.",
    "categories": [
        {"label": "protest", "definition": "An occupation, march, or strike."},
        {"label": "not_protest", "definition": "Any event that does not meet the criteria above."},
    ],
}


def test_validate_spec_accepts_a_valid_spec():
    validate_spec(VALID_SPEC)  # must not raise


def test_validate_spec_rejects_duplicate_labels():
    bad_spec = {**VALID_SPEC, "categories": [VALID_SPEC["categories"][0], VALID_SPEC["categories"][0]]}
    with pytest.raises(ValueError, match="duplicate category label"):
        validate_spec(bad_spec)


def test_validate_spec_rejects_missing_concept():
    bad_spec = {k: v for k, v in VALID_SPEC.items() if k != "concept"}
    with pytest.raises(ValueError, match="missing required field"):
        validate_spec(bad_spec)


def test_validate_spec_rejects_category_missing_definition():
    bad_spec = {**VALID_SPEC, "categories": [{"label": "protest"}]}
    with pytest.raises(ValueError, match="missing required field"):
        validate_spec(bad_spec)


def test_spec_to_yaml_string_then_spec_from_yaml_string_round_trips():
    yaml_text = spec_to_yaml_string(VALID_SPEC)

    round_tripped = spec_from_yaml_string(yaml_text)

    assert round_tripped == VALID_SPEC


def test_spec_to_yaml_string_rejects_invalid_spec():
    bad_spec = {**VALID_SPEC, "categories": []}
    with pytest.raises(ValueError, match="at least one category"):
        spec_to_yaml_string(bad_spec)


def test_codebook_from_yaml_string_works_on_output_of_spec_to_yaml_string():
    yaml_text = spec_to_yaml_string(VALID_SPEC)

    codebook = Codebook.from_yaml_string(yaml_text)

    assert set(codebook.schema.model_fields["category"].annotation.__args__) == {"protest", "not_protest"}


def test_from_yaml_file_loads_codebook_from_disk(tmp_path):
    path = tmp_path / "codebook.yaml"
    path.write_text(YAML_SOURCE, encoding="utf-8")

    codebook = Codebook.from_yaml_file(str(path))

    assert set(codebook.schema.model_fields["category"].annotation.__args__) == {
        "protest",
        "not_protest",
    }


# ---------------------------------------------------------------------------
# R1.1 step 2: variables / multi-label (spec: docs/superpowers/specs/
# 2026-09-13-r1.1-multi-variable-and-multi-label-codebooks-design.md)
# ---------------------------------------------------------------------------

from text_as_data.codebook import (  # noqa: E402  (grouped with the tests that use them)
    GOLD_EMPTY_SET_TOKEN,
    GOLD_SET_DELIMITER,
    PROMPT_TEMPLATE_VERSION,
    CodebookVariable,
    normalize_spec,
    normalized_spec_hash,
    variable_spec_hash,
)

SHORTHAND_YAML = """
concept: protest
description: A collective public event with a claim.
categories:
  - label: protest
    definition: Occupation, march or strike with a demand.
  - label: not_protest
    definition: Anything else.
"""

TWO_VARIABLE_YAML = """
concept: land_conflict_coverage
description: News coverage of agrarian conflicts.
variables:
  - name: event_type
    description: The main event the article reports. Exactly one applies.
    categories:
      - label: protest
        definition: An occupation, march or blockade with a demand.
      - label: violence
        definition: An attack or eviction as the central event.
      - label: other
        definition: Anything that fits none of the above.
  - name: sdg_goals
    description: Every SDG the conflict bears on. Select all that apply.
    multi_label: true
    max_labels: 2
    categories:
      - label: sdg_5
        definition: Gender is part of the claim or the harm.
      - label: sdg_15
        definition: Land, biome or territory is part of the conflict.
      - label: sdg_16
        definition: The state or courts are the arena of the conflict.
"""


def test_normalize_spec_turns_shorthand_into_one_main_variable_with_defaults():
    spec = spec_from_yaml_string(SHORTHAND_YAML)
    norm = normalize_spec(spec)
    assert norm["concept"] == "protest"
    assert norm["description"] == "A collective public event with a claim."
    assert norm["prompt_strategy"] == "per_variable"
    assert "categories" not in norm
    assert len(norm["variables"]) == 1
    v = norm["variables"][0]
    assert v["name"] == "main"
    assert v["description"] == "A collective public event with a claim."
    assert v["multi_label"] is False
    assert v["min_labels"] == 0
    assert v["max_labels"] is None
    assert v["evidence_granularity"] == "per_label"
    assert [c["label"] for c in v["categories"]] == ["protest", "not_protest"]


def test_normalize_spec_fills_defaults_on_explicit_variables_and_keeps_order():
    norm = normalize_spec(spec_from_yaml_string(TWO_VARIABLE_YAML))
    names = [v["name"] for v in norm["variables"]]
    assert names == ["event_type", "sdg_goals"]
    event_type, sdg = norm["variables"]
    assert event_type["multi_label"] is False and event_type["max_labels"] is None
    assert sdg["multi_label"] is True and sdg["min_labels"] == 0 and sdg["max_labels"] == 2
    assert sdg["evidence_granularity"] == "per_label"


def test_normalize_spec_fills_category_defaults():
    norm = normalize_spec(spec_from_yaml_string(SHORTHAND_YAML))
    c = norm["variables"][0]["categories"][0]
    assert c["positive_examples"] == [] and c["negative_examples"] == [] and c["boundary_notes"] == ""


def test_normalize_spec_does_not_mutate_its_input():
    spec = spec_from_yaml_string(SHORTHAND_YAML)
    before = yaml.safe_dump(spec, sort_keys=True)
    normalize_spec(spec)
    assert yaml.safe_dump(spec, sort_keys=True) == before


def test_normalize_spec_is_idempotent():
    norm = normalize_spec(spec_from_yaml_string(TWO_VARIABLE_YAML))
    assert normalize_spec(norm) == norm


def _two_var_spec(**variable_overrides):
    """TWO_VARIABLE_YAML as a dict with overrides applied to the sdg_goals variable."""
    spec = spec_from_yaml_string(TWO_VARIABLE_YAML)
    spec["variables"][1].update(variable_overrides)
    return spec


def test_validate_spec_accepts_the_two_variable_form():
    validate_spec(spec_from_yaml_string(TWO_VARIABLE_YAML))


def test_validate_spec_rejects_both_categories_and_variables_at_top_level():
    spec = spec_from_yaml_string(TWO_VARIABLE_YAML)
    spec["categories"] = [{"label": "x", "definition": "y"}]
    with pytest.raises(ValueError, match="exactly one of 'categories' or 'variables'"):
        validate_spec(spec)


def test_validate_spec_rejects_neither_categories_nor_variables():
    with pytest.raises(ValueError, match="exactly one of 'categories' or 'variables'"):
        validate_spec({"concept": "c", "description": "d"})


@pytest.mark.parametrize("bad_name", ["1abc", "has space", "has-dash", "has.dot", ""])
def test_validate_spec_rejects_invalid_variable_names(bad_name):
    with pytest.raises(ValueError, match="variable name"):
        validate_spec(_two_var_spec(name=bad_name))


@pytest.mark.parametrize("reserved", ["main", "category", "document_id", "rationale", "variable"])
def test_validate_spec_rejects_reserved_variable_names(reserved):
    with pytest.raises(ValueError, match="reserved"):
        validate_spec(_two_var_spec(name=reserved))


def test_validate_spec_rejects_duplicate_variable_names():
    with pytest.raises(ValueError, match="duplicate variable name"):
        validate_spec(_two_var_spec(name="event_type"))


def test_validate_spec_rejects_colliding_derived_export_columns():
    # `x` and `x_rationale` cannot coexist: x's rationale column would be
    # named exactly like the second variable's own label column.
    spec = spec_from_yaml_string(TWO_VARIABLE_YAML)
    spec["variables"][0]["name"] = "x"
    spec["variables"][1]["name"] = "x_rationale"
    with pytest.raises(ValueError, match="export column"):
        validate_spec(spec)


def test_validate_spec_requires_a_variable_description():
    with pytest.raises(ValueError, match="description"):
        validate_spec(_two_var_spec(description=""))


def test_validate_spec_rejects_non_boolean_multi_label():
    with pytest.raises(ValueError, match="multi_label"):
        validate_spec(_two_var_spec(multi_label="yes"))


def test_validate_spec_rejects_min_max_labels_on_a_single_label_variable():
    spec = spec_from_yaml_string(TWO_VARIABLE_YAML)
    spec["variables"][0]["max_labels"] = 1
    with pytest.raises(ValueError, match="only allowed when multi_label"):
        validate_spec(spec)


def test_validate_spec_rejects_evidence_granularity_on_a_single_label_variable():
    spec = spec_from_yaml_string(TWO_VARIABLE_YAML)
    spec["variables"][0]["evidence_granularity"] = "per_set"
    with pytest.raises(ValueError, match="only allowed when multi_label"):
        validate_spec(spec)


@pytest.mark.parametrize("granularity", ["per_label", "per_set"])
def test_validate_spec_accepts_both_evidence_granularities(granularity):
    validate_spec(_two_var_spec(evidence_granularity=granularity))


def test_validate_spec_rejects_unknown_evidence_granularity():
    with pytest.raises(ValueError, match="evidence_granularity"):
        validate_spec(_two_var_spec(evidence_granularity="per_document"))


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"min_labels": -1}, "non-negative integer"),
        ({"max_labels": 0.5}, "non-negative integer"),
        ({"min_labels": 3, "max_labels": 2}, "min_labels"),
        ({"max_labels": 4}, "max_labels"),  # only 3 categories
    ],
)
def test_validate_spec_rejects_inconsistent_label_bounds(overrides, message):
    with pytest.raises(ValueError, match=message):
        validate_spec(_two_var_spec(**overrides))


def test_validate_spec_rejects_multi_label_labels_that_break_the_gold_csv():
    spec = _two_var_spec()
    spec["variables"][1]["categories"][0]["label"] = f"sdg{GOLD_SET_DELIMITER}5"
    with pytest.raises(ValueError, match=re.escape(GOLD_SET_DELIMITER)):
        validate_spec(spec)
    spec = _two_var_spec()
    spec["variables"][1]["categories"][0]["label"] = GOLD_EMPTY_SET_TOKEN
    with pytest.raises(ValueError, match=re.escape(GOLD_EMPTY_SET_TOKEN)):
        validate_spec(spec)
    spec = _two_var_spec()
    spec["variables"][1]["categories"][0]["label"] = " sdg_5"
    with pytest.raises(ValueError, match="whitespace"):
        validate_spec(spec)


def test_validate_spec_allows_a_pipe_in_a_single_label_label():
    # Single-label variables never round-trip through a delimited cell.
    spec = spec_from_yaml_string(TWO_VARIABLE_YAML)
    spec["variables"][0]["categories"][0]["label"] = "a|b"
    validate_spec(spec)


def test_validate_spec_rejects_unknown_prompt_strategy():
    spec = spec_from_yaml_string(TWO_VARIABLE_YAML)
    spec["prompt_strategy"] = "sequential"
    with pytest.raises(ValueError, match="prompt_strategy"):
        validate_spec(spec)


@pytest.mark.parametrize("literal, expected", [("true", True), ("True", True), ("yes", True), ("false", False), ("off", False)])
def test_spec_from_yaml_string_restores_a_real_boolean_on_multi_label(literal, expected):
    # The bool-safe loader (which keeps `yes`/`no` *labels* as strings)
    # would otherwise hand validate_spec the string "true" for
    # `multi_label: true`; the YAML boundary re-applies PyYAML's own bool
    # table to that one key so authors get standard YAML behaviour.
    spec = spec_from_yaml_string(TWO_VARIABLE_YAML.replace("multi_label: true", f"multi_label: {literal}"))
    assert spec["variables"][1]["multi_label"] is expected
    assert spec["variables"][0].get("multi_label") is None  # untouched when absent
    # Labels are still not coerced.
    labels_spec = spec_from_yaml_string(SHORTHAND_YAML.replace("label: protest", "label: yes"))
    assert labels_spec["categories"][0]["label"] == "yes"


def test_validate_spec_still_reports_shorthand_errors_the_old_way():
    # Regression guard for the existing single-variable messages.
    with pytest.raises(ValueError, match="duplicate category label"):
        validate_spec({"concept": "c", "description": "d",
                       "categories": [{"label": "a", "definition": "x"}, {"label": "a", "definition": "y"}]})


def test_shorthand_codebook_is_byte_identical_to_the_pre_variables_behaviour():
    book = Codebook.from_yaml_string(SHORTHAND_YAML)
    assert len(book.variables) == 1
    v = book.variables[0]
    assert v.name == "main" and v.multi_label is False
    # Same schema title and field names as before step 2 -- the JSON schema
    # is embedded in the CLI prompt, so the title is part of the wire format.
    assert book.schema is v.schema
    assert book.schema.__name__ == "CodebookExtraction"
    assert list(book.schema.model_fields) == ["category", "rationale", "evidence_span"]
    # Same instructions text: no "Variable:" block for the shorthand.
    assert book.instructions == v.instructions
    assert book.instructions.startswith("Concept: protest\nA collective public event with a claim.\n\nCategories:\n")
    assert "Variable:" not in book.instructions


def test_two_variable_codebook_builds_one_schema_and_instructions_per_variable():
    book = Codebook.from_yaml_string(TWO_VARIABLE_YAML)
    assert [v.name for v in book.variables] == ["event_type", "sdg_goals"]
    assert book.prompt_strategy == "per_variable"
    # No single top-level schema/instructions for a multi-variable codebook.
    assert book.schema is None and book.instructions == ""

    event_type = book.variable("event_type")
    assert event_type.schema.__name__ == "EventTypeExtraction"
    assert list(event_type.schema.model_fields) == ["category", "rationale", "evidence_span"]
    assert event_type.labels == ["protest", "violence", "other"]
    assert "Variable: event_type\nThe main event the article reports. Exactly one applies." in event_type.instructions
    assert "Concept: land_conflict_coverage" in event_type.instructions
    assert "- protest: An occupation, march or blockade with a demand." in event_type.instructions
    assert "sdg_5" not in event_type.instructions  # other variables' categories are not leaked in

    with pytest.raises(KeyError):
        book.variable("nope")


def test_multi_label_per_label_schema_has_selections_with_per_label_evidence():
    book = Codebook.from_yaml_string(TWO_VARIABLE_YAML)
    sdg = book.variable("sdg_goals")
    assert sdg.multi_label is True and sdg.evidence_granularity == "per_label"
    fields = sdg.schema.model_fields
    assert list(fields) == ["selections", "rationale"]
    selection_model = fields["selections"].annotation.__args__[0]
    assert list(selection_model.model_fields) == ["label", "rationale", "evidence_span"]
    # min/max bounds are enforced by the schema itself, not only the prompt.
    schema_json = sdg.schema.model_json_schema()
    assert schema_json["properties"]["selections"]["maxItems"] == 2
    assert schema_json["properties"]["selections"]["minItems"] == 0
    # Enum of labels lives on the selection's `label`.
    parsed = sdg.schema.model_validate(
        {"selections": [{"label": "sdg_5", "rationale": "r", "evidence_span": "q"}], "rationale": "overall"}
    )
    assert parsed.selections[0].label == "sdg_5"
    with pytest.raises(Exception):
        sdg.schema.model_validate({"selections": [{"label": "not_a_label", "rationale": "r", "evidence_span": "q"}], "rationale": "x"})
    with pytest.raises(Exception):  # 3 > max_labels=2
        sdg.schema.model_validate({"selections": [
            {"label": "sdg_5", "rationale": "", "evidence_span": ""},
            {"label": "sdg_15", "rationale": "", "evidence_span": ""},
            {"label": "sdg_16", "rationale": "", "evidence_span": ""}], "rationale": "x"})


def test_multi_label_per_set_schema_has_a_labels_list_and_one_evidence_span():
    spec = _two_var_spec(evidence_granularity="per_set", max_labels=None)
    del spec["variables"][1]["max_labels"]
    book = Codebook._from_spec(spec)
    sdg = book.variable("sdg_goals")
    fields = sdg.schema.model_fields
    assert list(fields) == ["labels", "rationale", "evidence_span"]
    schema_json = sdg.schema.model_json_schema()
    assert "maxItems" not in schema_json["properties"]["labels"]
    parsed = sdg.schema.model_validate({"labels": ["sdg_5", "sdg_16"], "rationale": "r", "evidence_span": "q"})
    assert parsed.labels == ["sdg_5", "sdg_16"]


def test_multi_label_instructions_carry_the_parsimony_paragraph_and_bounds():
    book = Codebook.from_yaml_string(TWO_VARIABLE_YAML)
    text = book.variable("sdg_goals").instructions
    assert "Select every category whose definition is met, and only those." in text
    assert "If no category applies, return an empty list" in text
    assert "Select at most 2 categories." in text
    assert "Select at least" not in text  # min_labels is 0
    spec = _two_var_spec(min_labels=1, max_labels=2)
    text = Codebook._from_spec(spec).variable("sdg_goals").instructions
    assert "Select at least 1 category." in text and "Select at most 2 categories." in text
    # Single-label variables do not get the paragraph.
    assert "Select every category" not in book.variable("event_type").instructions


def test_per_set_instructions_ask_for_one_quote_for_the_set():
    spec = _two_var_spec(evidence_granularity="per_set")
    text = Codebook._from_spec(spec).variable("sdg_goals").instructions
    assert "Quote the single passage that best grounds the set as a whole." in text
    assert "Quote the specific passage that grounds each selected category." not in text


def test_variable_spec_hash_is_stable_across_yaml_reformatting_and_explicit_form():
    shorthand = Codebook.from_yaml_string(SHORTHAND_YAML).variables[0]
    reformatted = Codebook.from_yaml_string(
        "concept: protest\n"
        "description: 'A collective public event with a claim.'\n"
        "categories:\n"
        "- {label: protest, definition: 'Occupation, march or strike with a demand.', positive_examples: []}\n"
        "- {label: not_protest, definition: Anything else., boundary_notes: ''}\n"
    ).variables[0]
    assert shorthand.spec_hash == reformatted.spec_hash
    assert len(shorthand.spec_hash) == 64


def test_variable_spec_hash_changes_when_the_prompt_changes_and_not_otherwise():
    base = Codebook.from_yaml_string(TWO_VARIABLE_YAML)
    # Editing sdg_goals does not touch event_type's hash ...
    edited = _two_var_spec(max_labels=3)
    edited_book = Codebook._from_spec(edited)
    assert edited_book.variable("event_type").spec_hash == base.variable("event_type").spec_hash
    # ... but does change sdg_goals' own hash (max_labels is in the prompt and schema).
    assert edited_book.variable("sdg_goals").spec_hash != base.variable("sdg_goals").spec_hash
    # The codebook-level description is in every variable's prompt, so it is in every hash.
    spec = spec_from_yaml_string(TWO_VARIABLE_YAML)
    spec["description"] = "Changed."
    assert Codebook._from_spec(spec).variable("event_type").spec_hash != base.variable("event_type").spec_hash
    # evidence_granularity changes the schema, so it is in the hash.
    assert Codebook._from_spec(_two_var_spec(evidence_granularity="per_set")).variable("sdg_goals").spec_hash != base.variable("sdg_goals").spec_hash


def test_variable_spec_hash_includes_the_prompt_template_version(monkeypatch):
    import text_as_data.codebook as cb
    before = Codebook.from_yaml_string(SHORTHAND_YAML).variables[0].spec_hash
    monkeypatch.setattr(cb, "PROMPT_TEMPLATE_VERSION", PROMPT_TEMPLATE_VERSION + 1)
    after = Codebook.from_yaml_string(SHORTHAND_YAML).variables[0].spec_hash
    assert before != after


def test_normalized_spec_hash_equal_for_shorthand_and_its_explicit_form():
    spec = spec_from_yaml_string(SHORTHAND_YAML)
    explicit = normalize_spec(spec)
    assert normalized_spec_hash(spec) == normalized_spec_hash(explicit)


def test_spec_to_yaml_string_round_trips_the_variables_form():
    spec = spec_from_yaml_string(TWO_VARIABLE_YAML)
    text = spec_to_yaml_string(spec)
    again = spec_from_yaml_string(text)
    assert again == spec
    Codebook.from_yaml_string(text)  # loads
