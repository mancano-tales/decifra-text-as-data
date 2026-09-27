from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, BeforeValidator, Field, create_model


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


# Bumped whenever the fixed instruction text below changes (persona, the
# multi-label parsimony paragraph, list formatting). Part of every
# variable_spec_hash, so a wording change invalidates the extraction cache
# instead of silently serving answers produced by a different prompt.
PROMPT_TEMPLATE_VERSION = 1

# Gold-label CSV conventions for multi-label variables (spec §7.2). Labels
# of a multi-label variable may not contain the delimiter or equal the
# empty-set token, checked in validate_spec so the CSV parser never faces
# an ambiguous cell.
GOLD_SET_DELIMITER = "|"
GOLD_EMPTY_SET_TOKEN = "[]"

# The shorthand's implicit variable name, and every name a variable may not
# take because it would collide with a results/export column (spec §2.3).
SHORTHAND_VARIABLE_NAME = "main"
RESERVED_VARIABLE_NAMES = frozenset(
    {
        SHORTHAND_VARIABLE_NAME,
        "id", "run_id", "document_id", "document_snippet",
        "category", "categories", "rationale", "evidence_span",
        "variable", "tokens_used", "prompt_sent", "raw_response",
    }
)
_VARIABLE_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_PROMPT_STRATEGIES = ("per_variable", "joint")
_EVIDENCE_GRANULARITIES = ("per_label", "per_set")
# Suffixes appended to a variable name to form its export columns. Used by
# validate_spec's distinctness check; step 5 (app.py export) must use the
# same list.
EXPORT_COLUMN_SUFFIXES = ("", "_rationale", "_evidence_span", "_selections", "_evidence_verified")


def _normalize_category(category: dict) -> dict:
    return {
        "label": category["label"],
        "definition": category["definition"],
        "positive_examples": list(category.get("positive_examples") or []),
        "negative_examples": list(category.get("negative_examples") or []),
        "boundary_notes": category.get("boundary_notes") or "",
    }


def normalize_spec(spec: dict) -> dict:
    """Return a new spec dict in the explicit `variables:` form with every
    default filled in. The single-variable shorthand (top-level
    `categories:`) becomes one variable named `main` whose description is
    the codebook's. Does not validate -- call `validate_spec` first (it
    accepts both forms). Pure: the input is not mutated, and normalizing
    an already-normalized spec returns an equal dict, which is what makes
    the spec hashes below stable across YAML reformatting."""
    spec = copy.deepcopy(spec)
    if "variables" in spec:
        raw_variables = spec["variables"]
    else:
        raw_variables = [
            {
                "name": SHORTHAND_VARIABLE_NAME,
                "description": spec.get("description", ""),
                "categories": spec.get("categories", []),
            }
        ]
    variables = []
    for raw in raw_variables:
        variables.append(
            {
                "name": raw["name"],
                "description": raw["description"],
                "multi_label": bool(raw.get("multi_label", False)),
                "min_labels": raw.get("min_labels", 0) if raw.get("min_labels") is not None else 0,
                "max_labels": raw.get("max_labels"),
                "evidence_granularity": raw.get("evidence_granularity", "per_label"),
                "categories": [_normalize_category(c) for c in raw.get("categories", [])],
            }
        )
    return {
        "concept": spec.get("concept"),
        "description": spec.get("description"),
        "prompt_strategy": spec.get("prompt_strategy", "per_variable"),
        "variables": variables,
    }


def _validate_categories(categories, *, owner: str, multi_label: bool) -> list[str]:
    """Today's per-category rules, plus the multi-label gold-CSV rules.
    Returns the labels in order. `owner` names the variable in messages."""
    if not categories:
        raise ValueError(f"{owner} must define at least one category")
    labels: list[str] = []
    for category in categories:
        if not isinstance(category, dict):
            # YAML like `categories: ["protest", "not_protest"]` (a list of
            # bare strings instead of mappings) parses fine at the top
            # level, but each `category` is then a str, and `.get` below
            # would raise a raw AttributeError instead of a clean ValueError.
            raise ValueError(f"codebook category must be a YAML mapping (object), got {category!r}")
        label = category.get("label")
        # isinstance(str), not truthiness: an unquoted YAML integer label
        # (`label: 0`) must be rejected as "not a string", not confused
        # with a missing label -- `category` is a string everywhere
        # downstream (ExtractionRecord, the frontend, every example).
        if not isinstance(label, str) or not label:
            raise ValueError(f"codebook category label must be a non-empty string, got {label!r}")
        if not category.get("definition"):
            raise ValueError(f"category {label!r} missing required field: 'definition'")
        if multi_label:
            # A multi-label gold cell is `a|b|c`; these three rules are what
            # let the CSV parser split it without ever guessing.
            if GOLD_SET_DELIMITER in label:
                raise ValueError(
                    f"{owner}: label {label!r} contains {GOLD_SET_DELIMITER!r}, which is the "
                    f"gold-CSV set delimiter for multi-label variables"
                )
            if label == GOLD_EMPTY_SET_TOKEN:
                raise ValueError(
                    f"{owner}: label {label!r} is the gold-CSV empty-set token and cannot be a category"
                )
            if label != label.strip():
                raise ValueError(f"{owner}: label {label!r} has leading/trailing whitespace")
        labels.append(label)
    if len(set(labels)) != len(labels):
        raise ValueError(f"duplicate category label in {owner}: {labels}")
    return labels


def _validate_variable(raw: dict, index: int) -> None:
    if not isinstance(raw, dict):
        raise ValueError(f"variables[{index}] must be a YAML mapping (object), got {raw!r}")
    name = raw.get("name")
    if not isinstance(name, str) or not _VARIABLE_NAME_RE.match(name or ""):
        raise ValueError(
            f"variables[{index}]: variable name must match {_VARIABLE_NAME_RE.pattern} "
            f"(letters, digits, underscore; not starting with a digit), got {name!r}"
        )
    if name in RESERVED_VARIABLE_NAMES:
        raise ValueError(f"variable name {name!r} is reserved (results/export column or the shorthand name)")
    owner = f"variable {name!r}"
    if not raw.get("description"):
        raise ValueError(f"{owner} missing required field: 'description' (the question the LLM is asked)")

    multi_label = raw.get("multi_label", False)
    if not isinstance(multi_label, bool):
        raise ValueError(f"{owner}: multi_label must be true or false, got {multi_label!r}")
    for key in ("min_labels", "max_labels", "evidence_granularity"):
        if key in raw and not multi_label:
            raise ValueError(f"{owner}: {key!r} is only allowed when multi_label is true")

    labels = _validate_categories(raw.get("categories"), owner=owner, multi_label=multi_label)

    if multi_label:
        min_labels = raw.get("min_labels", 0)
        max_labels = raw.get("max_labels")
        for key, value in (("min_labels", min_labels), ("max_labels", max_labels)):
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{owner}: {key} must be a non-negative integer, got {value!r}")
        if max_labels is not None:
            if min_labels > max_labels:
                raise ValueError(f"{owner}: min_labels ({min_labels}) exceeds max_labels ({max_labels})")
            if max_labels > len(labels):
                raise ValueError(
                    f"{owner}: max_labels ({max_labels}) exceeds the number of categories ({len(labels)})"
                )
        granularity = raw.get("evidence_granularity", "per_label")
        if granularity not in _EVIDENCE_GRANULARITIES:
            raise ValueError(
                f"{owner}: evidence_granularity must be one of {list(_EVIDENCE_GRANULARITIES)}, got {granularity!r}"
            )


def validate_spec(spec: dict) -> None:
    """Validate a codebook spec dict -- the shared shape used by both the
    YAML file format and the structured codebook-editor API. Accepts the
    single-variable shorthand (top-level `categories:`) and the explicit
    `variables:` form (spec §2). Raises `ValueError` with a human-readable
    message on the first problem found. Both `Codebook.from_yaml_string`
    and `spec_to_yaml_string` call this, so the YAML format and the
    editor's JSON body can never validate differently."""
    if not isinstance(spec, dict):
        # A comments-only or blank YAML document parses to None (and a
        # bare scalar/list isn't a mapping either) -- without this check,
        # spec.get(...) raises a raw AttributeError instead of ValueError.
        raise ValueError(f"codebook spec must be a YAML mapping (object), got {spec!r}")
    if not spec.get("concept"):
        raise ValueError("codebook spec missing required field: 'concept'")
    if not spec.get("description"):
        raise ValueError("codebook spec missing required field: 'description'")

    has_categories = "categories" in spec
    has_variables = "variables" in spec
    if has_categories == has_variables:
        raise ValueError(
            "codebook must define exactly one of 'categories' or 'variables' "
            "(the single-variable shorthand vs. the explicit variables list)"
        )

    strategy = spec.get("prompt_strategy", "per_variable")
    if strategy not in _PROMPT_STRATEGIES:
        raise ValueError(f"prompt_strategy must be one of {list(_PROMPT_STRATEGIES)}, got {strategy!r}")

    if has_categories:
        # Shorthand: keep the historical messages ("codebook must define at
        # least one category", "duplicate category label in codebook").
        _validate_categories(spec.get("categories"), owner="codebook", multi_label=False)
        return

    variables = spec["variables"]
    if not isinstance(variables, list) or not variables:
        raise ValueError("'variables' must be a non-empty list")
    for index, raw in enumerate(variables):
        _validate_variable(raw, index)
    names = [v["name"] for v in variables]
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate variable name in codebook: {names}")
    derived: dict[str, str] = {}
    for name in names:
        for suffix in EXPORT_COLUMN_SUFFIXES:
            column = f"{name}{suffix}"
            if column in derived and derived[column] != name:
                raise ValueError(
                    f"variables {derived[column]!r} and {name!r} would both produce an export column "
                    f"named {column!r}; rename one of them"
                )
            derived.setdefault(column, name)


def _coerce_yaml_booleans(spec):
    """Restore real booleans on the one codebook field that *is* a boolean.

    `_CodebookYamlLoader` strips the YAML bool resolver so that labels like
    `yes`/`no` survive as strings -- but that also turns a variable's
    `multi_label: true` into the string `"true"`, which `validate_spec`
    (rightly) rejects as "not a boolean". This re-applies PyYAML's own
    bool table (`yes/no/true/false/on/off`, any case) to `multi_label`
    only, so YAML authors get the standard behaviour on that key while
    labels stay untouched. Anything else (a real bool from the editor's
    JSON body, an unrelated string like `"maybe"`) passes through and is
    left for `validate_spec` to reject with a clear message."""
    if not isinstance(spec, dict) or not isinstance(spec.get("variables"), list):
        return spec
    bool_values = yaml.constructor.SafeConstructor.bool_values
    for variable in spec["variables"]:
        if not isinstance(variable, dict):
            continue
        value = variable.get("multi_label")
        if isinstance(value, str) and value.lower() in bool_values:
            variable["multi_label"] = bool_values[value.lower()]
    return spec


def spec_from_yaml_string(source: str) -> dict:
    """Parse codebook YAML text into a spec dict, using the bool-safe
    loader. Used by both `Codebook.from_yaml_string` and by `app.py` to
    read a stored codebook's spec back for the editor's edit form."""
    return _coerce_yaml_booleans(yaml.load(source, Loader=_CodebookYamlLoader))


def spec_to_yaml_string(spec: dict) -> str:
    """Serialize a codebook spec dict to YAML text in the same shape
    `spec_from_yaml_string` reads back. Validates first, so a caller never
    persists an invalid spec as if it were valid YAML."""
    validate_spec(spec)
    return yaml.safe_dump(spec, allow_unicode=True, sort_keys=False)


_MULTI_LABEL_PARAGRAPH = (
    "Select every category whose definition is met, and only those. Do not add "
    "a category because the document is loosely related to it; a category "
    "applies only when its definition is satisfied. "
)
_PER_LABEL_QUOTE_SENTENCE = "Quote the specific passage that grounds each selected category. "
_PER_SET_QUOTE_SENTENCE = "Quote the single passage that best grounds the set as a whole. "
_EMPTY_SET_SENTENCE = (
    "If no category applies, return an empty list and explain why in the overall rationale."
)


def _pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_") if part)


def _build_single_label_schema(model_name: str, labels: list[str]) -> type[BaseModel]:
    # Fixed contract: `category`/`rationale`/`evidence_span` are relied on
    # by exact field name elsewhere (db.py's ExtractionRecord,
    # run_extraction, the results/gold/validation endpoints, the frontend)
    # -- renaming here breaks those call sites silently via AttributeError,
    # not at this layer. Renamed from the original Portuguese identifiers
    # on 2026-09-13 (R1.1 step 1); db.py migrates existing databases.
    return create_model(
        model_name,
        category=(Literal[tuple(labels)], Field(description="One of the codebook's category labels.")),
        rationale=(str, Field(description="Free-text rationale for the chosen category.")),
        evidence_span=(str, Field(description="Verbatim quote from the document that grounds the decision.")),
    )


def _dedupe_label_values(values):
    """Remove repeated string labels before list bounds are validated.

    A repeated label must not make an otherwise valid set exceed
    `max_labels`. Invalid non-string values are left for Pydantic's Literal
    validation to reject with its normal error.
    """
    if not isinstance(values, list):
        return values
    result = []
    seen = set()
    for value in values:
        if not isinstance(value, str) or value not in seen:
            result.append(value)
        if isinstance(value, str):
            seen.add(value)
    return result


def _dedupe_selection_values(values):
    """Deduplicate per-label selection objects by label, first occurrence wins."""
    if not isinstance(values, list):
        return values
    result = []
    seen = set()
    for value in values:
        label = value.get("label") if isinstance(value, dict) else getattr(value, "label", None)
        if not isinstance(label, str) or label not in seen:
            result.append(value)
        if isinstance(label, str):
            seen.add(label)
    return result


def _build_multi_label_schema(
    model_name: str, labels: list[str], *, min_labels: int, max_labels: int | None, evidence_granularity: str
) -> type[BaseModel]:
    list_kwargs = {"min_length": min_labels}
    if max_labels is not None:
        list_kwargs["max_length"] = max_labels
    if evidence_granularity == "per_set":
        label_list = Annotated[list[Literal[tuple(labels)]], BeforeValidator(_dedupe_label_values)]
        return create_model(
            model_name,
            labels=(
                label_list,
                Field(**list_kwargs, description="Every category whose definition is met, and only those. Empty if none applies."),
            ),
            rationale=(str, Field(description="Overall reasoning for the set as a whole, including near-miss categories considered and why they were not selected.")),
            evidence_span=(str, Field(description="Verbatim quote from the document that best grounds the set as a whole.")),
        )
    selection = create_model(
        f"{model_name.removesuffix('Extraction')}Selection",
        label=(Literal[tuple(labels)], Field(description="One selected category label.")),
        rationale=(str, Field(description="Why this label applies to this document.")),
        evidence_span=(str, Field(description="Verbatim quote from the document that grounds THIS label.")),
    )
    selection_list = Annotated[list[selection], BeforeValidator(_dedupe_selection_values)]
    return create_model(
        model_name,
        selections=(
            selection_list,
            Field(**list_kwargs, description="Every category whose definition is met, and only those. Empty if none applies."),
        ),
        rationale=(str, Field(description="Overall reasoning for the set as a whole, including near-miss categories considered and why they were not selected.")),
    )


def _build_instructions(concept: str, description: str, variable: dict) -> str:
    """The instructions block for one variable. For the shorthand `main`
    variable this is byte-identical to the pre-R1.1 text (no "Variable:"
    block), which keeps prompts -- and therefore the extraction cache --
    stable for every existing single-variable codebook."""
    lines = [f"Concept: {concept}", description.strip(), ""]
    if variable["name"] != SHORTHAND_VARIABLE_NAME:
        lines += [f"Variable: {variable['name']}", variable["description"].strip(), ""]
    lines.append("Categories:")
    for c in variable["categories"]:
        lines.append(f"- {c['label']}: {c['definition'].strip()}")
        for ex in c["positive_examples"]:
            lines.append(f'  Positive example: "{ex}"')
        for ex in c["negative_examples"]:
            lines.append(f'  Negative example: "{ex}"')
        if c["boundary_notes"]:
            lines.append(f"  Boundary notes: {c['boundary_notes'].strip()}")
    if variable["multi_label"]:
        quote = _PER_SET_QUOTE_SENTENCE if variable["evidence_granularity"] == "per_set" else _PER_LABEL_QUOTE_SENTENCE
        paragraph = _MULTI_LABEL_PARAGRAPH + quote + _EMPTY_SET_SENTENCE
        if variable["min_labels"] > 0:
            n = variable["min_labels"]
            paragraph += f" Select at least {n} {'category' if n == 1 else 'categories'}."
        if variable["max_labels"] is not None:
            n = variable["max_labels"]
            paragraph += f" Select at most {n} {'category' if n == 1 else 'categories'}."
        lines += ["", paragraph]
    return "\n".join(lines)


def variable_spec_hash(concept: str, description: str, variable: dict) -> str:
    """sha256 over the *normalized* variable spec plus the codebook-level
    preamble and PROMPT_TEMPLATE_VERSION -- everything that shapes this
    variable's prompt and schema, and nothing else. Reformatting the YAML,
    or editing another variable, does not change it (spec §4.3)."""
    payload = {
        "template": PROMPT_TEMPLATE_VERSION,
        "concept": concept,
        "description": description,
        "variable": variable,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def normalized_spec_hash(spec: dict) -> str:
    """sha256 over the whole normalized spec -- the joint-mode cache key and
    the reproducibility check's notion of "same codebook" (spec §4.3)."""
    return hashlib.sha256(
        json.dumps(normalize_spec(spec), sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@dataclass
class CodebookVariable:
    """One question the codebook asks of every document, with its own
    output schema, instructions block and cache-key hash."""

    name: str
    description: str
    categories: list[dict]
    multi_label: bool
    min_labels: int
    max_labels: int | None
    evidence_granularity: str
    schema: type[BaseModel]
    instructions: str
    spec_hash: str

    @property
    def labels(self) -> list[str]:
        return [c["label"] for c in self.categories]

    @classmethod
    def from_normalized(cls, concept: str, description: str, variable: dict) -> "CodebookVariable":
        labels = [c["label"] for c in variable["categories"]]
        model_name = (
            "CodebookExtraction" if variable["name"] == SHORTHAND_VARIABLE_NAME else f"{_pascal(variable['name'])}Extraction"
        )
        if variable["multi_label"]:
            schema = _build_multi_label_schema(
                model_name, labels,
                min_labels=variable["min_labels"], max_labels=variable["max_labels"],
                evidence_granularity=variable["evidence_granularity"],
            )
        else:
            schema = _build_single_label_schema(model_name, labels)
        return cls(
            name=variable["name"],
            description=variable["description"],
            categories=variable["categories"],
            multi_label=variable["multi_label"],
            min_labels=variable["min_labels"],
            max_labels=variable["max_labels"],
            evidence_granularity=variable["evidence_granularity"],
            schema=schema,
            instructions=_build_instructions(concept, description, variable),
            spec_hash=variable_spec_hash(concept, description, variable),
        )


@dataclass
class Codebook:
    """A theoretical construct operationalized as one or more LLM-extractable
    schemas.

    A codebook bundles what must travel together: for each *variable*, the
    output schema (what columns end up in the structured table) and the
    instructions (the theoretical definition of each category -- the part a
    domain expert actually authors); plus optional worked examples
    (few-shot) that pin down edge cases.

    `schema`/`instructions` at the top level are the single-variable
    convenience: populated when the codebook has exactly one variable
    (every codebook before R1.1, and the `Codebook(schema=..., instructions=...)`
    constructor used by tests/examples), `None`/`""` otherwise -- callers
    handling multi-variable codebooks go through `variables`.
    """

    schema: type[BaseModel] | None = None
    instructions: str = ""
    examples: list[dict] = field(default_factory=list)
    concept: str = ""
    description: str = ""
    prompt_strategy: str = "per_variable"
    variables: list[CodebookVariable] = field(default_factory=list)

    _PERSONA = (
        "You are a careful annotator applying a fixed coding scheme. "
        "Follow the instructions below exactly as written, even when a "
        "case looks similar to a more common or generic concept. Do not "
        "substitute your own default definition for the one given.\n\n"
    )

    def variable(self, name: str) -> CodebookVariable:
        for v in self.variables:
            if v.name == name:
                return v
        raise KeyError(f"codebook has no variable {name!r}; variables: {[v.name for v in self.variables]}")

    def _resolve_variable_instructions(self, variable) -> str:
        if variable is None:
            if len(self.variables) > 1:
                raise ValueError(
                    f"codebook has {len(self.variables)} variables; pass variable= to build_messages "
                    f"(one of {[v.name for v in self.variables]})"
                )
            return self.instructions
        if isinstance(variable, str):
            variable = self.variable(variable)
        return variable.instructions

    def build_messages(
        self, text: str, variable: "str | CodebookVariable | None" = None, include_persona: bool = True
    ) -> list[dict]:
        # `include_persona` exists to let an ablation test isolate the fixed
        # persona line's own effect from the codebook's actual instructions
        # -- see docs/research/2026-09-02_llm_pipeline_verification_methodology.md's
        # "provenance of the fixed persona line" section, which flagged that
        # this line (present since the project's very first commit, before
        # any specific codebook existed) had never been measured with vs.
        # without. Defaults to the existing behavior (persona included).
        # `variable` selects which variable's instructions to send; omitted
        # = the single variable.
        instructions = self._resolve_variable_instructions(variable)
        system = f"{self._PERSONA}{instructions}" if include_persona else instructions
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
        norm = normalize_spec(spec)
        variables = [
            CodebookVariable.from_normalized(norm["concept"], norm["description"], v) for v in norm["variables"]
        ]
        single = variables[0] if len(variables) == 1 else None
        return cls(
            schema=single.schema if single else None,
            instructions=single.instructions if single else "",
            concept=norm["concept"],
            description=norm["description"],
            prompt_strategy=norm["prompt_strategy"],
            variables=variables,
        )
