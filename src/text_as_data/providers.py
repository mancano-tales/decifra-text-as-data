from __future__ import annotations

import json
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError


@dataclass
class ProviderResult:
    """A provider's answer plus the audit trail of what actually produced
    it: the exact prompt sent and the raw (pre-parsing) response received.

    Without this, `run_extraction` could only persist the *parsed*
    categoria/justificativa/trecho_evidencia -- there was no way to prove,
    after the fact, what an LLM was actually asked or actually said before
    `CliProvider._extract_json` stripped any surrounding prose. For a tool
    whose whole premise is that LLM coding must be auditable and
    reproducible (see AGENTS.md's validation rationale), silently
    discarding that is a real gap, not a cosmetic one."""

    parsed: BaseModel
    prompt: str
    raw_response: str
    tokens_used: int | None = None


class Provider(ABC):
    """Something that can turn (messages, schema) into a validated schema
    instance, plus the prompt/raw-response audit trail (see
    `ProviderResult`)."""

    @abstractmethod
    def extract(self, messages: list[dict], schema: type[BaseModel]) -> ProviderResult:
        ...


class ApiKeyProvider(Provider):
    """The reliable path: an `instructor`-patched client that enforces the
    schema at the API level via tool/function calling."""

    def __init__(self, client: Any, model: str):
        self._client = client
        self._model = model

    def extract(self, messages: list[dict], schema: type[BaseModel]) -> ProviderResult:
        result = self._client.chat.completions.create(
            model=self._model,
            response_model=schema,
            messages=messages,
            max_retries=3,
        )
        # instructor enforces the schema via function-calling, so there is
        # no separate "raw text" distinct from the parsed result the way
        # CliProvider has raw CLI stdout -- the parsed JSON itself is the
        # most honest thing to record as what was actually received.
        usage = getattr(getattr(result, "_raw_response", None), "usage", None)
        tokens = getattr(usage, "total_tokens", None)
        if tokens is None and usage is not None:
            input_tokens = getattr(usage, "input_tokens", None)
            output_tokens = getattr(usage, "output_tokens", None)
            if input_tokens is not None and output_tokens is not None:
                tokens = input_tokens + output_tokens
        return ProviderResult(
            tokens_used=tokens,
            parsed=result,
            prompt=json.dumps(messages, ensure_ascii=False),
            raw_response=result.model_dump_json(),
        )


def make_api_key_provider(vendor: str, model: str, api_key: str | None = None) -> ApiKeyProvider:
    """Build an ApiKeyProvider for a real vendor. Not used in tests — tests
    construct ApiKeyProvider directly with a fake client."""
    import instructor

    if vendor == "anthropic":
        from anthropic import Anthropic

        client = instructor.from_anthropic(Anthropic(api_key=api_key))
    elif vendor == "openai":
        from openai import OpenAI

        client = instructor.from_openai(OpenAI(api_key=api_key))
    else:
        raise ValueError(f"unknown vendor: {vendor!r} (expected 'anthropic' or 'openai')")

    return ApiKeyProvider(client=client, model=model)


class CliProvider(Provider):
    """Best-effort path: shells out to an already-installed CLI (e.g. the
    Claude Code CLI, `claude -p`, or a Codex-style CLI) instead of a billed
    API key. No API-level schema enforcement — the schema is requested in
    the prompt, and the response is parsed as JSON. Less reliable than
    ApiKeyProvider; retry-on-malformed-output is the caller's job
    (extraction.py), not this class's."""

    def __init__(
        self, command: list[str], runner=subprocess.run, timeout: int = 180, prompt_mode: str = "stdin"
    ):
        resolved = shutil.which(command[0])
        if resolved is not None:
            command = [resolved, *command[1:]]
        self._command = command
        self._runner = runner
        self._timeout = timeout
        if prompt_mode not in ("stdin", "arg"):
            raise ValueError(f"prompt_mode must be 'stdin' or 'arg', got {prompt_mode!r}")
        self._prompt_mode = prompt_mode

    def extract(self, messages: list[dict], schema: type[BaseModel]) -> ProviderResult:
        prompt = self._build_prompt(messages, schema)
        if self._prompt_mode == "arg":
            # Some CLIs (e.g. Google Antigravity's `agy -p "<prompt>"`) take
            # the prompt as a trailing argument rather than reading stdin --
            # `agy -p` with no argument errors "flag needs an argument"
            # instead of blocking on stdin the way `claude -p` does.
            result = self._runner(
                [*self._command, prompt],
                input=None,
                capture_output=True,
                encoding="utf-8",
                timeout=self._timeout,
            )
        else:
            result = self._runner(
                self._command,
                input=prompt,
                capture_output=True,
                encoding="utf-8",
                timeout=self._timeout,
            )
        if result.returncode != 0:
            raise RuntimeError(f"CLI command failed (exit {result.returncode}): {result.stderr}")
        json_str = self._extract_json(result.stdout, schema)
        parsed = schema.model_validate_json(json_str)
        # raw_response is the CLI's full stdout, not just the extracted
        # JSON candidate -- e.g. any surrounding prose _extract_json
        # stripped out is exactly the kind of thing worth being able to
        # inspect later when a result looks off.
        return ProviderResult(parsed=parsed, prompt=prompt, raw_response=result.stdout)

    _INSTRUCTIONS_EVIDENCE_DELIMITER = "--- FIM DAS INSTRUÇÕES — TEXTO A CLASSIFICAR ABAIXO ---"

    @staticmethod
    def _build_prompt(messages: list[dict], schema: type[BaseModel]) -> str:
        # `Codebook.build_messages` always appends the actual document to
        # classify as the final message (after any system instructions and
        # few-shot examples) -- true for every codebook, not just V7's.
        # Flattening everything with a bare "\n\n" join gives a CLI model
        # no structural signal for where fixed instructions end and the
        # variable, per-document evidence begins, unlike a real chat API
        # where role separation (system/user) already marks that boundary.
        # An explicit delimiter right before the last message restores
        # that signal for the CLI path specifically.
        parts = [m["content"] for m in messages[:-1]]
        if parts:
            # Only insert the delimiter when there's actually a preceding
            # instructions/example block to mark the end of -- a
            # single-message call (just the text to classify, no system
            # instructions) has nothing to delimit against, and prefixing
            # a marker onto the caller's only content would be pure noise.
            parts.append(f"{CliProvider._INSTRUCTIONS_EVIDENCE_DELIMITER}\n\n{messages[-1]['content']}")
        else:
            parts.append(messages[-1]["content"])
        schema_json = json.dumps(schema.model_json_schema())
        parts.append(
            "Respond with ONLY a single JSON object matching this JSON Schema, "
            f"and no other text before or after it:\n{schema_json}"
        )
        return "\n\n".join(parts)

    @staticmethod
    def _extract_json(text: str, schema: type[BaseModel]) -> str:
        """Find the substring of `text` that is a top-level `{...}` object
        validating against `schema`, and return it verbatim.

        CLI output in "best-effort" mode often wraps the answer in prose,
        and that prose can itself contain other JSON-shaped fragments (e.g.
        a CLI "thinking out loud" about the schema before answering, or a
        wrapper object like `{"result": {...}}`). A naive
        first-`{`-to-last-`}` regex would splice unrelated fragments
        together into one invalid blob. Instead, this scans the text for
        each top-level JSON object (see `_json_candidates`) and returns the
        first one that actually validates against `schema` — so a decoy
        fragment, or a nested sub-object that happens to also validate, is
        skipped in favor of the real top-level answer.
        """
        for candidate in CliProvider._json_candidates(text):
            try:
                schema.model_validate_json(candidate)
            except ValidationError:
                continue
            return candidate
        raise ValueError(f"no JSON object found in CLI output: {text!r}")

    @staticmethod
    def _json_candidates(text: str) -> list[str]:
        """Return every top-level `{...}` substring of `text` that is
        itself valid JSON, scanning left to right and skipping past each
        match found (so a nested `{...}` inside an already-matched object
        is never re-tried as its own candidate).

        Hand-counting braces to find a candidate's span is not
        string-aware: a `{` or `}` inside a JSON string value (e.g. a
        quoted source excerpt or a stray brace in free text) would be
        mistaken for structural nesting and either truncate or extend the
        span incorrectly. Instead, this tries `json.JSONDecoder.raw_decode`
        at each unconsumed `{` position — the real JSON parser, which
        already understands string boundaries, escapes, and nesting
        correctly. Skipping to the end of every successful parse (rather
        than trying the next character regardless) keeps candidates
        top-level only: a CLI response wrapped in a named key like
        `{"result": {...}}` yields one candidate (the outer object), not
        also its nested `{...}` value.
        """
        decoder = json.JSONDecoder()
        candidates: list[str] = []
        skip_until = 0
        for i, ch in enumerate(text):
            if i < skip_until or ch != "{":
                continue
            try:
                _, end = decoder.raw_decode(text, i)
            except json.JSONDecodeError:
                continue
            candidates.append(text[i:end])
            skip_until = end
        return candidates
