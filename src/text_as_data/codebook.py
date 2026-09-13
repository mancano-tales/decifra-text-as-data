from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import yaml
from pydantic import BaseModel, Field, create_model


class _CodebookYamlLoader(yaml.SafeLoader):
    """SafeLoader with the YAML 1.1 implicit-bool resolver disabled.

    Without this, unquoted category labels like `yes`/`no`/`on`/`off` (in
    any case) are parsed by PyYAML as Python booleans instead of strings,
    which silently corrupts labels and only surfaces later as a confusing
    Pydantic error. Codebook authors shouldn't have to know to quote
    reserved words, so we strip the bool resolver here instead.
    """


_CodebookYamlLoader.yaml_implicit_resolvers = {
    key: [resolver for resolver in resolvers if resolver[0] != "tag:yaml.org,2002:bool"]
    for key, resolvers in _CodebookYamlLoader.yaml_implicit_resolvers.items()
}


def validate_spec(spec: dict) -> None:
    """Validate a codebook spec dict -- the shared shape used by both the
    YAML file format and the structured codebook-editor API. Raises
    `ValueError` with a human-readable message on the first problem found.
    Both `Codebook.from_yaml_string` and `spec_to_yaml_string` call this,
    so the YAML format and the editor's JSON body can never validate
    differently."""
    if not isinstance(spec, dict):
        # A comments-only or blank YAML document parses to None (and a
        # bare YAML scalar/list parses to something that isn't a mapping
        # either) -- without this check, spec.get(...) below raises a raw
        # AttributeError instead of the ValueError every other invalid
        # input in this function produces.
        raise ValueError(f"codebook spec must be a YAML mapping (object), got {spec!r}")
    if not spec.get("concept"):
        raise ValueError("codebook spec missing required field: 'concept'")
    if not spec.get("description"):
        raise ValueError("codebook spec missing required field: 'description'")
    if not spec.get("categories"):
        raise ValueError("codebook must define at least one category")

    labels = []
    for category in spec["categories"]:
        if not isinstance(category, dict):
            # YAML like `categories: ["protest", "not_protest"]` (a list of
            # bare strings instead of mappings) parses fine at the top
            # level -- `spec.get("categories")` is truthy -- but each
            # `category` is then a str, and `category.get(...)` below
            # raises a raw AttributeError instead of a clean ValueError.
            raise ValueError(f"codebook category must be a YAML mapping (object), got {category!r}")
        label = category.get("label")
        # Deliberately isinstance(str), not just `not label` -- an unquoted
        # YAML integer label (e.g. `label: 0`) is falsy-adjacent under a
        # bare truthiness check (`not 0` is True) and would be rejected
        # with the same message as a genuinely missing label, instead of
        # this project's actual requirement: a non-empty string, since
        # `category` is a string everywhere downstream (ExtractionRecord,
        # the frontend, every codebook example in AGENTS.md).
        if not isinstance(label, str) or not label:
            raise ValueError(f"codebook category label must be a non-empty string, got {label!r}")
        if not category.get("definition"):
            raise ValueError(f"category {category.get('label')!r} missing required field: 'definition'")
        labels.append(category["label"])

    if len(set(labels)) != len(labels):
        raise ValueError(f"duplicate category label in codebook: {labels}")


def spec_from_yaml_string(source: str) -> dict:
    """Parse codebook YAML text into a spec dict, using the bool-safe
    loader. Used by both `Codebook.from_yaml_string` and by `app.py` to
    read a stored codebook's spec back for the editor's edit form."""
    return yaml.load(source, Loader=_CodebookYamlLoader)


def spec_to_yaml_string(spec: dict) -> str:
    """Serialize a codebook spec dict to YAML text in the same shape
    `spec_from_yaml_string` reads back. Validates first, so a caller never
    persists an invalid spec as if it were valid YAML."""
    validate_spec(spec)
    return yaml.safe_dump(spec, allow_unicode=True, sort_keys=False)


@dataclass
class Codebook:
    """A theoretical construct operationalized as an LLM-extractable schema.

    A codebook bundles three things that must travel together: the output
    schema (what columns end up in the structured table), the instructions
    (the theoretical definition of each category — the part a domain expert
    actually authors), and a handful of worked examples (few-shot) that pin
    down edge cases the instructions alone tend to leave ambiguous.
    """

    schema: type[BaseModel]
    instructions: str
    examples: list[dict] = field(default_factory=list)

    _PERSONA = (
        "You are a careful annotator applying a fixed coding scheme. "
        "Follow the instructions below exactly as written, even when a "
        "case looks similar to a more common or generic concept. Do not "
        "substitute your own default definition for the one given.\n\n"
    )

    def build_messages(self, text: str, include_persona: bool = True) -> list[dict]:
        # `include_persona` exists to let an ablation test isolate the fixed
        # persona line's own effect from the codebook's actual instructions
        # -- see docs/research/2026-09-02_llm_pipeline_verification_methodology.md's
        # "provenance of the fixed persona line" section, which flagged that
        # this line (present since the project's very first commit, before
        # any specific codebook existed) had never been measured with vs.
        # without. Defaults to the existing behavior (persona included).
        system = f"{self._PERSONA}{self.instructions}" if include_persona else self.instructions
        messages = [{"role": "system", "content": system}]
        for example in self.examples:
            messages.append({"role": "user", "content": example["text"]})
            messages.append(
                {"role": "assistant", "content": example["output"].model_dump_json()}
                if isinstance(example["output"], BaseModel)
                else {"role": "assistant", "content": str(example["output"])}
            )
        messages.append({"role": "user", "content": text})
        return messages

    @classmethod
    def from_yaml_string(cls, source: str) -> "Codebook":
        spec = spec_from_yaml_string(source)
        return cls._from_spec(spec)

    @classmethod
    def from_yaml_file(cls, path: str) -> "Codebook":
        with open(path, encoding="utf-8") as f:
            return cls.from_yaml_string(f.read())

    @classmethod
    def _from_spec(cls, spec: dict) -> "Codebook":
        validate_spec(spec)

        # Fixed contract: `category`/`rationale`/`evidence_span` are relied
        # on by exact field name elsewhere (db.py's ExtractionRecord,
        # run_extraction, the results/gold/validation endpoints, the
        # frontend) -- renaming here breaks those call sites silently via
        # AttributeError, not at this layer. Renamed from the original
        # Portuguese identifiers on 2026-09-13 (R1.1 step 1); db.py migrates
        # existing databases in place.
        labels = [c["label"] for c in spec["categories"]]
        schema = create_model(
            "CodebookExtraction",
            category=(Literal[tuple(labels)], Field(description="One of the codebook's category labels.")),
            rationale=(str, Field(description="Free-text rationale for the chosen category.")),
            evidence_span=(
                str,
                Field(description="Verbatim quote from the document that grounds the decision."),
            ),
        )

        lines = [f"Concept: {spec['concept']}", spec["description"].strip(), "", "Categories:"]
        for c in spec["categories"]:
            lines.append(f"- {c['label']}: {c['definition'].strip()}")
            for ex in c.get("positive_examples", []):
                lines.append(f'  Positive example: "{ex}"')
            for ex in c.get("negative_examples", []):
                lines.append(f'  Negative example: "{ex}"')
            if c.get("boundary_notes"):
                lines.append(f"  Boundary notes: {c['boundary_notes'].strip()}")
        instructions = "\n".join(lines)

        return cls(schema=schema, instructions=instructions)
