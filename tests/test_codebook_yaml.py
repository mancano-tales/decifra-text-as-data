import pytest

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
