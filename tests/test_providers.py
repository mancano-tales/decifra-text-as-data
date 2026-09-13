from pydantic import BaseModel

from text_as_data.providers import ApiKeyProvider


class Label(BaseModel):
    categoria: str


class FakeChatCompletions:
    def __init__(self):
        self.calls = 0

    def create(self, model, response_model, messages, max_retries):
        self.calls += 1
        return response_model(categoria="protest")


class FakeInstructorClient:
    def __init__(self):
        self.chat = type("Chat", (), {"completions": FakeChatCompletions()})()


def test_api_key_provider_delegates_to_instructor_client():
    fake_client = FakeInstructorClient()
    provider = ApiKeyProvider(client=fake_client, model="fake-model")

    result = provider.extract(messages=[{"role": "user", "content": "x"}], schema=Label)

    assert result.parsed.categoria == "protest"
    assert fake_client.chat.completions.calls == 1


def test_api_key_provider_records_prompt_and_raw_response_for_audit():
    # Without this, a run against a real API-key vendor has no way to prove
    # after the fact what was actually sent/received -- see ProviderResult.
    fake_client = FakeInstructorClient()
    provider = ApiKeyProvider(client=fake_client, model="fake-model")
    messages = [{"role": "system", "content": "instructions"}, {"role": "user", "content": "the evidence text"}]

    result = provider.extract(messages=messages, schema=Label)

    assert "the evidence text" in result.prompt
    assert result.raw_response == result.parsed.model_dump_json()


import shutil
import subprocess

import pytest

from text_as_data.providers import CliProvider


def _fake_runner(stdout: str, returncode: int = 0):
    def runner(command, input, capture_output, encoding, timeout):
        assert encoding == "utf-8"
        return subprocess.CompletedProcess(args=command, returncode=returncode, stdout=stdout, stderr="")

    return runner


def test_cli_provider_parses_json_from_stdout():
    runner = _fake_runner('Here is the answer:\n{"categoria": "protest"}\nDone.')
    provider = CliProvider(command=["fake-cli", "-p"], runner=runner)

    result = provider.extract(messages=[{"role": "user", "content": "x"}], schema=Label)

    assert result.parsed.categoria == "protest"


def test_cli_provider_raises_on_nonzero_exit():
    runner = _fake_runner("boom", returncode=1)
    provider = CliProvider(command=["fake-cli"], runner=runner)

    with pytest.raises(RuntimeError, match="CLI command failed"):
        provider.extract(messages=[{"role": "user", "content": "x"}], schema=Label)


def test_cli_provider_raises_on_missing_json():
    runner = _fake_runner("no json here")
    provider = CliProvider(command=["fake-cli"], runner=runner)

    with pytest.raises(ValueError, match="no JSON object found"):
        provider.extract(messages=[{"role": "user", "content": "x"}], schema=Label)


def test_cli_provider_skips_non_matching_json_fragment_before_the_answer():
    # Realistic "best-effort" CLI output: an earlier JSON-shaped fragment
    # (e.g. the CLI thinking out loud about the schema) precedes the real
    # answer. A naive first-`{`-to-last-`}` regex would splice these two
    # fragments into one invalid blob and raise a confusing
    # pydantic.ValidationError instead of finding the real answer.
    runner = _fake_runner(
        'Let me check the schema first: {"note": "checking the schema"}\n\n'
        'Here is my answer:\n{"categoria": "protest"}'
    )
    provider = CliProvider(command=["fake-cli"], runner=runner)

    result = provider.extract(messages=[{"role": "user", "content": "x"}], schema=Label)

    assert result.parsed.categoria == "protest"


def test_cli_provider_handles_unmatched_brace_inside_json_string_value():
    # Adversarial but realistic: a free-text field (e.g. a quoted source
    # excerpt) contains a stray unmatched `}` inside the JSON string
    # itself. A hand-rolled brace-depth counter treats that in-string `}`
    # as closing the top-level object, producing a truncated, invalid
    # candidate and never resuming — even though the JSON is perfectly
    # valid. Preceded by an unrelated decoy fragment to also confirm
    # schema-validated selection still skips past it.
    runner = _fake_runner(
        'Let me check the schema first: {"note": "checking the schema"}\n\n'
        'Here is my answer:\n'
        '{"justificativa": "cost > 100} threshold exceeded", "categoria": "protest"}'
    )
    provider = CliProvider(command=["fake-cli"], runner=runner)

    result = provider.extract(messages=[{"role": "user", "content": "x"}], schema=Label)

    assert result.parsed.categoria == "protest"


def test_cli_provider_prefers_top_level_object_over_nested_sub_object():
    # A CLI that wraps its answer in a named key (e.g. `{"result": {...}}`,
    # or here a `wrapper` key containing a nested object that itself
    # happens to validate against the schema) must not have that inner
    # object mistaken for the real, top-level answer. Trying
    # `raw_decode` at every `{` position -- including ones nested inside
    # an already-parsed object -- would find the inner object first and
    # return it instead of the real top-level answer that follows.
    runner = _fake_runner(
        '{"wrapper": {"justificativa": "inner one", "categoria": "inner_match"}, '
        '"outer_note": "irrelevant"}\n'
        '{"justificativa": "outer one", "categoria": "outer_match"}'
    )
    provider = CliProvider(command=["fake-cli"], runner=runner)

    result = provider.extract(messages=[{"role": "user", "content": "x"}], schema=Label)

    assert result.parsed.categoria == "outer_match"


def test_cli_provider_resolves_command_via_path(monkeypatch):
    # On Windows, `claude` installed via npm resolves to a `.cmd` shim, not
    # a `.exe`. subprocess.run(["claude", "-p"], shell=False) does not
    # search PATHEXT the way a real shell does, so it fails to find the
    # executable even though `claude` works fine typed directly in a
    # terminal. CliProvider must resolve the command's first element via
    # shutil.which() at construction time so the resolved absolute path is
    # what actually gets invoked.
    monkeypatch.setattr(shutil, "which", lambda name: r"C:\fake\path\claude.cmd" if name == "claude" else None)

    provider = CliProvider(command=["claude", "-p"], runner=_fake_runner("{}"))

    assert provider._command == [r"C:\fake\path\claude.cmd", "-p"]


def test_cli_provider_keeps_original_command_when_not_found_on_path(monkeypatch):
    # If shutil.which can't find the command, keep the original name rather
    # than swallowing the error -- subprocess.run will then raise its own
    # clear FileNotFoundError naming the command, which is the right
    # failure mode for a genuinely-missing CLI.
    monkeypatch.setattr(shutil, "which", lambda name: None)

    provider = CliProvider(command=["totally-missing-cli", "-p"], runner=_fake_runner("{}"))

    assert provider._command == ["totally-missing-cli", "-p"]


def test_cli_provider_passes_utf8_encoding_to_runner():
    # subprocess.run(..., text=True) with no explicit `encoding` decodes
    # stdout/stderr using the locale default encoding (cp1252 on Windows),
    # silently corrupting non-ASCII output (e.g. accented Portuguese text)
    # even though the `claude` CLI actually emits UTF-8. extract() must
    # pass encoding="utf-8" explicitly so decoding is correct regardless of
    # the host locale.
    captured_kwargs = {}

    def capturing_runner(command, input, capture_output, encoding, timeout):
        captured_kwargs["encoding"] = encoding
        return subprocess.CompletedProcess(
            args=command, returncode=0, stdout='{"categoria": "protest"}', stderr=""
        )

    provider = CliProvider(command=["fake-cli"], runner=capturing_runner)
    provider.extract(messages=[{"role": "user", "content": "x"}], schema=Label)

    assert captured_kwargs["encoding"] == "utf-8"


def test_cli_provider_passes_prompt_as_trailing_arg_when_configured(monkeypatch):
    # `agy -p "<prompt>"` (Google Antigravity CLI) errors "flag needs an
    # argument" if given no value and nothing on stdin -- unlike `claude
    # -p`, which blocks reading the prompt from stdin. prompt_mode="arg"
    # must append the prompt to the command list instead of piping it in.
    monkeypatch.setattr(shutil, "which", lambda name: None)
    captured = {}

    def capturing_runner(command, input, capture_output, encoding, timeout):
        captured["command"] = command
        captured["input"] = input
        return subprocess.CompletedProcess(args=command, returncode=0, stdout='{"categoria": "protest"}', stderr="")

    provider = CliProvider(command=["agy", "-p"], runner=capturing_runner, prompt_mode="arg")
    result = provider.extract(messages=[{"role": "user", "content": "x"}], schema=Label)

    assert result.parsed.categoria == "protest"
    assert captured["command"][:2] == ["agy", "-p"]
    assert captured["command"][2].startswith("x")
    assert captured["input"] is None


def test_cli_provider_rejects_unknown_prompt_mode():
    with pytest.raises(ValueError, match="prompt_mode"):
        CliProvider(command=["fake-cli"], runner=_fake_runner("{}"), prompt_mode="carrier-pigeon")


def test_cli_provider_records_exact_prompt_and_full_raw_stdout_for_audit():
    # The whole point of ProviderResult for CliProvider: prove later what
    # was actually sent (not a reconstruction someone has to trust) and
    # what the CLI actually said back, including any surrounding prose
    # _extract_json stripped out to find the answer.
    stdout = 'Let me think about this.\n{"categoria": "protest"}\nDone thinking.'
    runner = _fake_runner(stdout)
    provider = CliProvider(command=["fake-cli", "-p"], runner=runner)
    messages = [{"role": "system", "content": "codebook instructions here"}, {"role": "user", "content": "the news article text"}]

    result = provider.extract(messages=messages, schema=Label)

    assert "codebook instructions here" in result.prompt
    assert "the news article text" in result.prompt
    assert result.raw_response == stdout  # full stdout, not just the extracted JSON candidate


def test_cli_provider_inserts_delimiter_between_instructions_and_evidence():
    # A flat CLI prompt gives up the role separation a real chat API has --
    # without an explicit marker, a model has no structural signal for
    # where fixed instructions end and the variable, per-document evidence
    # begins. See docs/research/2026-09-02_llm_pipeline_verification_methodology.md.
    captured = {}

    def capturing_runner(command, input, capture_output, encoding, timeout):
        captured["input"] = input
        return subprocess.CompletedProcess(args=command, returncode=0, stdout='{"categoria": "protest"}', stderr="")

    provider = CliProvider(command=["fake-cli"], runner=capturing_runner)
    messages = [{"role": "system", "content": "codebook instructions here"}, {"role": "user", "content": "the evidence text"}]

    provider.extract(messages=messages, schema=Label)

    prompt = captured["input"]
    delimiter_pos = prompt.index(CliProvider._INSTRUCTIONS_EVIDENCE_DELIMITER)
    assert prompt.index("codebook instructions here") < delimiter_pos < prompt.index("the evidence text")


def test_cli_provider_omits_delimiter_when_there_is_no_preceding_instructions_block():
    # A single-message call (no separate system/instructions message) has
    # nothing for a delimiter to separate -- the prompt should be exactly
    # the message content, unprefixed, matching pre-delimiter behavior.
    captured = {}

    def capturing_runner(command, input, capture_output, encoding, timeout):
        captured["input"] = input
        return subprocess.CompletedProcess(args=command, returncode=0, stdout='{"categoria": "protest"}', stderr="")

    provider = CliProvider(command=["fake-cli"], runner=capturing_runner)

    provider.extract(messages=[{"role": "user", "content": "x"}], schema=Label)

    assert captured["input"].startswith("x")
    assert CliProvider._INSTRUCTIONS_EVIDENCE_DELIMITER not in captured["input"]


def test_cli_provider_decodes_non_ascii_output_correctly():
    # End-to-end sanity check that non-ASCII text (e.g. Portuguese
    # accented characters from the V7 pilot corpus) survives the round
    # trip through extract() unmangled.
    text = "instituições"
    runner = _fake_runner('{"categoria": "' + text + '"}')
    provider = CliProvider(command=["fake-cli"], runner=runner)

    result = provider.extract(messages=[{"role": "user", "content": "x"}], schema=Label)

    assert result.parsed.categoria == text


import text_as_data.providers as providers_module
from text_as_data.providers import PromptTooLongError


def _never_called_runner(command, input, capture_output, encoding, timeout):
    raise AssertionError("runner must not be invoked when the prompt cannot fit on the command line")


def test_cli_provider_arg_mode_raises_before_invoking_cli_when_prompt_exceeds_limit(monkeypatch):
    # Windows caps a process command line at 32,767 characters. In
    # prompt_mode="arg" the whole prompt rides on the command line, so a
    # long document made subprocess.run raise a bare
    # `FileNotFoundError: [WinError 206] The filename or extension is too
    # long` -- a message that says nothing about documents or prompts.
    # The provider must pre-flight the length and raise its own clear
    # error *without* ever spawning the CLI.
    monkeypatch.setattr(shutil, "which", lambda name: None)
    provider = CliProvider(
        command=["agy", "-p"], runner=_never_called_runner, prompt_mode="arg", max_arg_length=500
    )

    with pytest.raises(PromptTooLongError):
        provider.extract(messages=[{"role": "user", "content": "x" * 1000}], schema=Label)


def test_cli_provider_prompt_too_long_error_is_a_value_error_with_actionable_message(monkeypatch):
    # run_extraction's per-document loop catches `Exception` and stores
    # str(exc) as the row's error -- so the message itself is what the
    # researcher will read in the Results table. It must name the actual
    # length, the limit, and what to do about it.
    monkeypatch.setattr(shutil, "which", lambda name: None)
    provider = CliProvider(
        command=["agy", "-p"], runner=_never_called_runner, prompt_mode="arg", max_arg_length=500
    )

    with pytest.raises(ValueError) as excinfo:
        provider.extract(messages=[{"role": "user", "content": "x" * 1000}], schema=Label)

    exc = excinfo.value
    assert isinstance(exc, PromptTooLongError)
    message = str(exc)
    assert exc.actual_length > 500
    assert exc.prompt_length >= 1000
    assert str(exc.actual_length) in message
    assert str(exc.prompt_length) in message
    assert "500" in message
    assert "stdin" in message
    assert "shorten" in message or "split" in message or "chunk" in message


def test_cli_provider_arg_mode_under_limit_still_invokes_runner(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    captured = {}

    def capturing_runner(command, input, capture_output, encoding, timeout):
        captured["command"] = command
        return subprocess.CompletedProcess(args=command, returncode=0, stdout='{"categoria": "protest"}', stderr="")

    provider = CliProvider(command=["agy", "-p"], runner=capturing_runner, prompt_mode="arg", max_arg_length=5000)
    result = provider.extract(messages=[{"role": "user", "content": "x" * 100}], schema=Label)

    assert result.parsed.categoria == "protest"
    assert captured["command"][:2] == ["agy", "-p"]


def test_cli_provider_stdin_mode_ignores_arg_length_limit():
    # The limit is a command-line concern only. Piping through stdin has
    # no such ceiling, so even an explicitly tiny max_arg_length must not
    # affect stdin mode.
    captured = {}

    def capturing_runner(command, input, capture_output, encoding, timeout):
        captured["input"] = input
        return subprocess.CompletedProcess(args=command, returncode=0, stdout='{"categoria": "protest"}', stderr="")

    provider = CliProvider(command=["fake-cli"], runner=capturing_runner, prompt_mode="stdin", max_arg_length=10)
    result = provider.extract(messages=[{"role": "user", "content": "x" * 100_000}], schema=Label)

    assert result.parsed.categoria == "protest"
    assert len(captured["input"]) > 100_000


def test_cli_provider_arg_mode_default_limit_is_windows_only(monkeypatch):
    # Default: 32_000 on Windows (a safety margin under the 32,767 hard
    # cap), unlimited elsewhere (POSIX ARG_MAX is orders of magnitude
    # larger). Exercised on any host by patching the module's view of
    # sys.platform.
    monkeypatch.setattr(shutil, "which", lambda name: None)

    monkeypatch.setattr(providers_module.sys, "platform", "win32")
    win = CliProvider(command=["agy", "-p"], runner=_never_called_runner, prompt_mode="arg")
    assert win._max_arg_length == 32_000
    with pytest.raises(PromptTooLongError):
        win.extract(messages=[{"role": "user", "content": "x" * 40_000}], schema=Label)

    monkeypatch.setattr(providers_module.sys, "platform", "linux")
    posix = CliProvider(command=["agy", "-p"], runner=_fake_runner('{"categoria": "protest"}'), prompt_mode="arg")
    assert posix._max_arg_length is None
    result = posix.extract(messages=[{"role": "user", "content": "x" * 40_000}], schema=Label)
    assert result.parsed.categoria == "protest"
