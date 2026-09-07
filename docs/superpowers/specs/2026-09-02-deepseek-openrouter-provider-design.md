# DeepSeek + OpenRouter provider support (Design)

> Decided 2026-09-02 via brainstorming with the author. Scope: add
> DeepSeek and OpenRouter as real API-key-mode vendors in the actual
> backend (`src/text_as_data/providers.py` + `app.py`), not the
> `examples/toy_example` demo script — explicitly chosen by the author
> since the security requirement ("secure without leaking API keys")
> only matters for the code path that handles real user data.

## Why

`AGENTS.md`'s provider layer already documents API-key mode as
vendor-agnostic in principle ("OpenAI and/or Anthropic via the
`instructor` SDK pattern"), but `providers.py::make_api_key_provider`
only implements those two. DeepSeek and OpenRouter are both
OpenAI-compatible (same Chat Completions request/response shape), so
this is a small extension, not a new integration pattern.

## Vendor dispatch

`make_api_key_provider(vendor, model, api_key=None)` gains two branches,
both using `instructor.from_openai(OpenAI(...))` — the same client class
already used for `"openai"`, pointed at a different `base_url`:

```python
_VENDOR_BASE_URLS = {
    "deepseek": "https://api.deepseek.com",
    "openrouter": "https://openrouter.ai/api/v1",
}
_VENDOR_ENV_VARS = {
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}
```

Both `base_url` values are hardcoded module-level constants — **never**
accepted from a request, env var, or any other caller-supplied input.
This is the load-bearing security property: `instructor`/`openai`'s
`OpenAI(api_key=..., base_url=...)` sends the `Authorization: Bearer
<api_key>` header to whatever `base_url` it's given, so a
caller-controlled `base_url` would let a malicious request redirect the
real key to an attacker-controlled host (SSRF-shaped key exfiltration).
Fixing it in code, not just by convention, is what makes this safe
regardless of what a future caller passes.

## Vendor inference (`app.py::_vendor_for_model`)

`_MODEL_PREFIX_TO_VENDOR` gains `"deepseek": "deepseek"` (DeepSeek's own
models are `deepseek-chat`, `deepseek-reasoner`, etc. — a clean prefix,
same pattern as `"claude"`/`"gpt"`).

OpenRouter has no single prefix: its model ids are always
`<upstream-vendor>/<model>` (`anthropic/claude-3-opus`,
`deepseek/deepseek-chat`, `google/gemini-2.0-flash`, `meta-llama/llama-3.3-70b-instruct`,
...). No native Anthropic/OpenAI/DeepSeek model id ever contains `/`, so
`"/" in model` is used as the OpenRouter signal — checked *after* the
prefix table, so a bare `deepseek-chat` (no slash) still resolves to the
native `deepseek` vendor rather than being misrouted.

```python
def _vendor_for_model(model: str) -> str:
    for prefix, vendor in _MODEL_PREFIX_TO_VENDOR.items():
        if model.startswith(prefix):
            return vendor
    if "/" in model:
        return "openrouter"
    raise HTTPException(422, detail=...)
```

## Credentials — security model

Same trust boundary as the existing `anthropic`/`openai` vendors,
extended, not redesigned:

- Keys live only in server-side environment variables
  (`DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`), read once inside
  `make_api_key_provider`. Never accepted from `CreateRunRequest` or any
  other HTTP input — the frontend has no field for it today and this
  design doesn't add one.
- A missing env var raises a clear `ValueError` (caught by the same
  `HTTPException` wrapping pattern `get_provider_dependency` already
  uses for `_vendor_for_model`'s own errors) instead of constructing a
  client with `api_key=None` and failing later with a confusing 401.
- Verified (reading the installed `openai` SDK's source, not assumed):
  `APIStatusError.__init__` stores the failing `httpx.Request` (which
  carries the `Authorization` header) as `self.request`, but `str(exc)` —
  the only thing this codebase ever does with a provider exception, in
  `extraction.py`'s per-document handler (`error_message = str(exc)`) —
  returns only `self.message`, built from the response body. The request
  object, and therefore the key, is never included in `str(exc)`. This
  means the existing error-handling path is already safe for the two new
  vendors without any additional redaction code.
- `provider_detail` (persisted on `RunRecord`, shown in
  `GET /runs/{id}/disclosure`) is set from `request.model` in API-key
  mode today, not from anything key-related — unaffected by this change.

## Testing

- `providers.py`: `make_api_key_provider(vendor="deepseek"/"openrouter",
  ...)` builds a client whose underlying `OpenAI` instance has the
  expected `base_url` — checked via the constructed client object, no
  real network call.
- `app.py`: extend the existing `_vendor_for_model` test coverage with a
  `deepseek-chat` case and an `anthropic/claude-3-opus`-shaped
  (slash-containing) case resolving to `"openrouter"`.
- A missing-env-var case for both new vendors, asserting a clear error
  rather than a raw SDK exception.

## Out of scope

No frontend UI changes (`RunForm.tsx` doesn't collect API keys today and
this design doesn't add that surface), no changes to CLI mode, no
`examples/toy_example` updates (explicit author decision — that script
is a demo, not the code path handling real data).
