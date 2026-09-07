# CatLLM Deep Dive: Primary-Source Verification and Honest Comparison to Cifra

**Date**: 2026-09-02
**Target**: `chrissoria/cat-llm` (GitHub), the `catllm.com` marketing site, and the actual
published PyPI engine packages the GitHub repo depends on but does not contain
(`cat-stack`, `cat-claws`).
**Supersedes**: nothing on record — see "Correcting the record" below. This file is a
new, standalone deep dive; it does not edit
`2026-09-02_landscape_competitive_analysis_and_related_software.md`, which is left as
historical record per instructions.

## Methodology

- Cloned `https://github.com/chrissoria/cat-llm` into a scratch directory via
  `git clone`. Commit read: `5481e28e27be83896bcbadba2f9878ed62f04276`
  ("README: note API vs Agent-SDK route effect on raw label dispersal"),
  2026-08-05.
- Read every top-level file and directory in that clone: `pyproject.toml`,
  `ARCHITECTURE.md`, `CHANGELOG.md`, `app/` (the Streamlit GUI +
  `app/desktop/` packaging), `.github/workflows/build-desktop.yml`,
  `src/catllm/__init__.py` + `src/cat_llm/__init__.py` (the actual Python
  package this repo ships), `r-package/*/R/*.R` (the R wrappers),
  `stata-package/` (a Stata wrapper), `academic_examples/paper.md`.
- **Critical structural discovery, made by actually trying to read the code
  instead of trusting `ARCHITECTURE.md`'s description of it**: the GitHub
  repo's own `src/catllm/__init__.py` is a 200-line meta-package that does
  `from catstack import classify, extract, explore, ...` — the real engine
  (`classify()`, `extract()`, the provider layer, prompt construction,
  JSON-schema handling, Ollama/CLI-subscription plumbing) is **not source
  code that lives in this GitHub repository at all**. It is published as
  separate PyPI packages (`cat-stack`, `cat-survey`, `cat-vader`,
  `cat-ademic`, `cat-pol`, `cat-web`, `cat-cog`, `cat-claws`) that
  `pyproject.toml` merely pins as dependencies (`dependencies = ["cat-stack>=2.5.1", ...]`,
  `pyproject.toml:26-34`). `ARCHITECTURE.md` in the repo describes a
  `src/catllm/classify.py` / `text_functions_ensemble.py` / `_providers.py`
  module structure that **does not exist in this repo's `src/catllm/`
  directory** — it is stale documentation describing the engine's internal
  structure from before it was split out into the `cat-stack` PyPI package.
  To do a genuine primary-source read rather than repeat that
  documentation-vs-reality gap, I ran `pip download cat-stack cat-claws
  --no-deps` (versions `2.5.1` and `0.3.1`, the floors pinned by this
  commit's `pyproject.toml`), unzipped the wheels, and read that code
  directly — ~22,100 lines across `catstack/*.py` plus `catclaws/*.py`. All
  claims below about prompt construction, JSON-schema enforcement, Ollama,
  CLI/subscription execution, and caching are grounded in that engine code,
  not in the GitHub repo's stub or its stale `ARCHITECTURE.md`. File
  citations below of the form `_providers.py:1338` refer to this
  `cat-stack==2.5.1` / `cat-claws==0.3.1` source, not to anything in the
  `cat-llm` git repo.
- Fetched `catllm.com` via WebFetch for the desktop-app platform-availability
  and validation-benchmark claims made on the marketing site specifically
  (since, per the point above, the actual desktop app and validation
  benchmark are not fully documented in the GitHub repo's own README).
- Read Cifra's own `AGENTS.md`, `src/text_as_data/codebook.py`,
  `src/text_as_data/providers.py`, `src/text_as_data/validation.py` in full
  as the comparison baseline.

## Correcting the record

The task that produced this document assumed an existing shallow paragraph
about CatLLM lived in `docs/research/2026-09-02_landscape_competitive_analysis_and_related_software.md`,
section "2.5". **That section does not exist.** A full read of that file (179
lines) and a repo-wide case-insensitive grep for `CatLLM|cat-llm|catllm|Soria`
across the entire `cifra-text-as-data` working tree turned up **zero
matches** anywhere in the repository. Whatever the earlier "not very sharp"
agent wrote about CatLLM, it was never actually committed or saved to this
file (or any file) in this repo — the landscape doc's section 2 lists eight
other GitHub tools (QCA-AID, quallm, CHAIR, Potato, AQDA, llm_tracker,
DeTAILS, gpt_annotate) and CatLLM is not among them.

There is accordingly nothing to "verify or correct" claim-by-claim — this
document is the first primary-source record of CatLLM in this repository,
not a correction of a prior one. This is itself worth flagging to the user:
the premise that a shallow CatLLM paragraph needed correcting appears to be
a false memory or a mix-up with a different research thread, not a
verified fact about this repo's contents.

---

## 1. Architecture: what CatLLM actually is

CatLLM is not one codebase — it is an **ecosystem of packages sharing one
engine**, published separately:

- **The engine**: `cat-stack` (PyPI, `catstack` import name) — 22,143 lines
  across `classify.py`, `extract.py`, `explore.py`, `summarize.py`,
  `collapse_themes.py`, `text_functions.py`,
  `text_functions_ensemble.py` (4,721 lines, the largest module),
  `pdf_functions.py`, `image_functions.py`, `_providers.py` (2,249 lines —
  every LLM vendor's payload shaping, retries, Ollama, and CLI/subscription
  dispatch), `_batch.py` (async batch-API support), `_embeddings.py`,
  `_tiebreaker.py`, `prompt_tune.py`, `_pilot_test.py`.
- **Domain wrappers**: `cat-survey`, `cat-vader` (social media), `cat-ademic`
  (academic text), `cat-pol` (policy/political text — includes
  `list_sources`/`fetch_source`, a source-retrieval helper), `cat-web`,
  `cat-cog` (a completely different thing: CERAD cognitive-drawing-test
  scoring, `cerad_drawn_score` — image-based dementia-screening scoring, not
  text classification at all). Each is a thin domain-specific prompt/prefix
  layer over the same `cat-stack` engine functions (confirmed by reading
  `r-package/cat.stack/R/classify.R`'s docstring: "Wraps the Python
  `cat_stack.classify()` function").
- **The subscription/agent backend**: `cat-claws` (PyPI, `catclaws` import
  name) — a separate small package (5 files) implementing the
  Claude-Agent-SDK and OpenAI-Codex-SDK adapters used for subscription-based
  (non-API-key) execution. Details in section 5 below.
- **`cat-llm` itself** (the GitHub repo, `src/catllm/__init__.py`, 200
  lines) is purely a re-export meta-package: `pip install cat-llm` pulls in
  all of the above and flattens their public functions into one namespace
  (`classify_survey`, `classify_social`, `classify_academic`, etc.).
- **R**: `r-package/cat.stack/`, `cat.survey/`, `cat.vader/`, `cat.ademic/`,
  `cat.pol/`, `cat.web/`, `cat.cog/`, plus a `cat.llm` meta-package —
  eight separate R packages, each a `reticulate`-style wrapper calling the
  same Python engine (confirmed via docstrings; not independently
  reimplemented in R).
- **Stata**: `stata-package/catllm*.ado` — `.ado` command wrappers, almost
  certainly shelling out to the same Python engine per-command (not
  independently read in depth, lower priority given Cifra has no Stata
  target).
- **A Streamlit GUI** (`app/`, ~15 files) — a full web app (Explore/Extract/
  Classify/Summarize/CERAD pages, model selection, history, cost estimation,
  visualizations) built on top of the same `cat-stack` engine functions, and
  **packaged as a native macOS desktop app** (`app/desktop/`, see section 7).

**What this means for comparison**: CatLLM is a much larger, more mature,
multi-language distribution surface than Cifra (Python + R + Stata + a
shipped desktop app across many research domains, not just one general
codebook engine). But the "codebook editor as the most important screen"
product philosophy Cifra is built around, and the audit/validation
apparatus, are architecturally a different thing entirely — sections below
go through why.

## 2. Codebook-equivalent, or not?

**Finding: there is no codebook abstraction, named or unnamed, in the actual
code.** A repo-wide grep for `codebook` (case-insensitive) across all of
`cat-stack` and `cat-claws` source returns **zero matches**. `classify()`'s
signature (`catstack/classify.py:126`) takes `categories: list` — a bare
list of category name strings. There is no dataclass, Pydantic model, YAML
schema, or JSON file format anywhere in the engine that bundles a category
with a definition, positive/negative examples, and boundary notes the way
Cifra's `Codebook` dataclass (`src/text_as_data/codebook.py:90-172`) does.

The one thing that looks adjacent is `category_descriptions: dict = None`
(`classify.py:179`), documented at `classify.py:361-364`: *"Optional dict
mapping category names to richer text descriptions for embedding
similarity... Only used when embeddings=True."* Verified by tracing every
use of that parameter (`grep -rn category_descriptions catstack/*.py`): it
is consumed **only** by `_embeddings.py`'s `compute_embedding_scores()`, to
build a richer string for cosine-similarity scoring against a sentence
embedding model — a completely separate optional feature
(`embedding_tiebreaker`) for resolving 50/50 ensemble ties. It is **not**
injected into the LLM classification prompt at all. Confirmed by reading
the actual prompt builder, `build_text_classification_prompt()`
(`text_functions_ensemble.py:1246-1316`): the prompt is built from
`categories_str` — literally *"Formatted string of categories (numbered
list)"* per its own docstring — plus a generic `description` (context about
the whole task, not per-category) and up to six freeform `example1..6`
strings that are not tied to any specific category. A category the LLM
actually sees is a bare label; no definition, no boundary notes, no
per-category worked example ever reaches the model.

`catllm.com`'s marketing copy does use the word "codebook" loosely ("either
consume an existing codebook or induce one from a sample of responses;
categories are not required up front") — but this is describing the
category *list* (which can be hand-supplied or auto-discovered via
`explore()`), not a structured per-category definition object. On the
actual code, "codebook" on catllm.com means "list of category names," full
stop — a materially different (and much thinner) thing than Cifra's
`concept` + `description` + per-category `label`/`definition`/
`positive_examples`/`negative_examples`/`boundary_notes` YAML contract.

**One place CatLLM does have something*-like* a boundary-note mechanism**:
`_category_analysis.py`'s `has_other_category()` / `check_category_verbosity()`
(imported into `classify.py:31`) — these check whether the user's category
list already includes a catch-all "other" bucket and warn if category names
are too verbose, but this is input-list hygiene, not concept operationalization.

## 3. Structured output, rationale, evidence span

**Schema enforcement**: real, and provider-native — `use_json_schema: bool =
True` (`classify.py:163`) drives `build_json_schema()`
(`_utils.py:99-124` / re-exported from `text_functions.py:117`), which is
passed as `json_schema` into `UnifiedLLMClient.complete()`
(`_providers.py:922`) and turned into each vendor's native strict-mode
JSON-schema/`response_format` payload (`_build_anthropic_payload`,
`_build_google_payload`, `_build_openai_payload`,
`_providers.py:931-954`), with an explicit carve-out at `_providers.py:990`
for the three providers that only support loose `json_object` mode (Ollama,
HuggingFace, Mistral). This is comparable in spirit to Cifra's
`instructor`-enforced Pydantic schema for `ApiKeyProvider` — both force
valid JSON at the API level for providers that support it.

**But the shape of that schema is fundamentally different.** CatLLM's
`build_json_schema()` produces `{"1": {"type":"string","enum":["0","1"]},
"2": {...}, ...}` — one binary present/absent flag per category, keyed by
position (`_utils.py:108-113`). This is a **multi-label indicator vector**,
not Cifra's single `categoria` enum. There is **no `rationale` field and no
`evidence_span`/quote field anywhere in the enforced schema** — confirmed
by reading `build_text_classification_prompt()`'s `json_instruction`
strings (`text_functions_ensemble.py:1283-1288`): *"Provide your answer in
JSON format where the category number is the key and '1' if present, '0' if
not"* — nothing about justification or a verbatim quote. `chain_of_thought`
(`classify.py:136`) asks the model to reason step-by-step *before* emitting
the JSON block, but that reasoning is prose the parser discards when it
extracts the trailing JSON object (`_extract_balanced_json`,
`_utils.py:127-159`) — it is not captured as a structured, auditable field
alongside each decision the way Cifra's `justificativa`/`trecho_evidencia`
are. This is a concrete, citable gap relative to exactly the finding
Halterman & Keith (and the Marston et al. 46-model study Cifra's own
`AGENTS.md` cites) warn about: forcing a verbatim evidence quote and
rationale is what makes LLM coding decisions auditable and catches models
substituting their own generic definition for the codebook's. CatLLM's
default output has no such field built in.

## 4. Validation / kappa machinery

**Finding: none exists in the shipped code.** A repo-wide, case-insensitive
grep for `kappa|cohen|precision_recall|f1_score|krippendorff|gwet` across
all of `cat-stack` and `cat-claws` returns exactly one hit, and it is not
code: `cat_claws-0.3.1.dist-info/METADATA` (the README shipped in the
`cat-claws` wheel) contains one sentence — *"On the 24-row synthetic parity
run (2026-07-11, `benchmarks/parity_run.py`) claude-sonnet-5 and gpt-5.5
agreed on 96/96 cells (Cohen's kappa 1.000, 0 errors)"* — describing a
one-off cross-*provider* parity benchmark script (not shipped in the
package; referenced by path only), not a reusable validation function a
user of the library can call against their own gold-standard human labels.

The closest thing that does ship is `_pilot_test.py`'s `compute_metrics()`
(`_pilot_test.py:13-51`), used by `prompt_tune()` (an automatic
prompt-optimization loop, section 6 below) and `classify(pilot_test=True)`.
It computes raw accuracy, sensitivity (= recall), and precision — hand-rolled
arithmetic over TP/FP/FN/TN counts, **not chance-corrected, no kappa, no F1,
no per-category breakdown beyond the aggregate cell-level numbers**. More
importantly, its input (`corrections`) is not an imported gold-standard
dataset compared against stored predictions after the fact — it is live
human corrections collected through a browser UI *during* a pilot run
(`collect_corrections()`), consumed immediately and not persisted as a
reusable gold-label table. There is no equivalent anywhere in the codebase
of Cifra's `human_labels` table, `agreement_report()`
(`validation.py:9-85`, computing accuracy + Cohen's kappa via
`sklearn.metrics.cohen_kappa_score` + per-label precision/recall/F1 +
a persisted, browsable mismatch list), or a dedicated Validation screen.
CatLLM's "validation" is an interactive prompt-improvement loop, not a
post-hoc scientific agreement report against a gold standard a researcher
can inspect, export, or cite.

`catllm.com`'s claim of *"88% to 99% agreement with human coders across 30+
LLMs"*, *"calibrated against the consensus of double-blind coding by
sociologists and demographers"* is a **research-paper benchmark result**
(pointing at `academic_examples/paper.md`/`paper.pdf`, a companion academic
paper, not the library itself) — confirmed by grepping `paper.md` for the
same kappa/agreement terms: zero hits, meaning even that companion paper
(at least in its Markdown form in this repo) doesn't visibly show its
statistical methodology in the file I could read as plain text; the
underlying rigor is not verifiable from the GitHub repo's own contents. The
figure is a claim about a specific study's results, not a software feature
a Cifra-equivalent user gets by running the tool on their own corpus.

## 5. Execution model: CLI-subscription support and Ollama depth

This is the area where CatLLM is genuinely more mature than Cifra's single
`CliProvider`, and worth the closest, most honest look.

**Three distinct subscription/agent code paths**, not one:
1. **`claude-code`** (`_providers.py:1168-1243`, `_call_claude_cli`) — the
   direct CLI-subprocess analogue of Cifra's `CliProvider`: builds
   `cmd = ["claude", "-p", "--output-format", "text", "--model", ..., user_prompt]`
   and calls `subprocess.run(cmd, capture_output=True, text=True, timeout=120)`.
2. **`claude-agent`** and **`codex-agent`** — routed through
   `_call_agent_backend()` (`_providers.py:1245+`) into the separate
   `cat-claws` package's `ClaudeAdapter`/`CodexAdapter`
   (`catclaws/_adapters/claude.py`), which uses the **`claude_agent_sdk`**
   Python SDK's `query()`/`ClaudeAgentOptions` — not a subprocess shelling
   raw text at all. This is a materially different, more robust mechanism
   than either Cifra's or CatLLM's own `claude-code` CLI path: it gets
   structured `RateLimitEvent`/`ResultMessage` objects instead of
   string-sniffing stderr for rate-limit wording, explicit `max_turns=1`
   / `allowed_tools=[]` / `setting_sources=[]` **session sealing** (so
   running classification from inside a git repo does not leak that repo's
   `CLAUDE.md`/project settings into the classification call — a
   correctness concern Cifra's raw-stdin `CliProvider` does not address at
   all), and an explicit `ANTHROPIC_API_KEY` env-blank
   (`claude.py:105-106`) to force subscription billing over an inherited
   API key. This SDK-based path is a genuinely better idea than raw CLI
   shelling for the "run on my subscription, not a metered key" use case,
   and is worth Cifra taking seriously as a second CLI-mode implementation
   option, not just a nice-to-have.
3. Both `claude-code` and the `cat-claws` agent adapters are **keyless by
   design** (subscription auth), matching Cifra's stated rationale for
   `CliProvider` exactly — CatLLM independently arrived at the same
   "researcher already pays for a CLI subscription" argument
   (`CHANGELOG.md`'s `[3.2.0]` entry: *"classification through a Claude
   *subscription* (no API key) works out of the box"*).

**A convergent bug, found independently by both projects**: Cifra's
`AGENTS.md` documents finding and fixing two Windows-specific bugs in its
own `CliProvider` — (a) `subprocess.run(["claude", "-p"], ...)` failing with
`FileNotFoundError: [WinError 2]` because `claude` resolves to an npm
`.cmd` shim that Windows's `CreateProcess` won't exec without `shell=True`
or a resolved path, fixed via `shutil.which()` in `__init__`; (b) an
implicit-encoding bug from `text=True` instead of `encoding="utf-8"`,
corrupting accented characters. **CatLLM's `_call_claude_cli`
(`_providers.py:1168-1243`) has both of the same bug patterns, unfixed as
of the version read**: it builds `cmd = ["claude", ...]` and calls
`subprocess.run(cmd, ...)` with no `shutil.which()` resolution and no
`shell=True` (it does catch the resulting `FileNotFoundError` gracefully
with an install-hint message at line 1231-1235, rather than crashing raw —
better failure handling than a crash, but the underlying Windows
path-resolution problem is not fixed the way Cifra's is), and it calls
`subprocess.run(cmd, capture_output=True, text=True, timeout=120)` at line
1208-1213 with the same bare `text=True` (no explicit `encoding="utf-8"`)
that caused Cifra's mojibake bug. This was not verified by actually running
it on Windows in this session (no `claude` CLI subscription available in
this environment to reproduce end-to-end), so it is reported as "the same
code pattern Cifra independently found to be broken," not as an
independently-reproduced failure — but the pattern match is exact and the
citation is precise. A third, CatLLM-specific weakness in the same
function: the user prompt is passed as a **trailing positional CLI
argument** (`cmd.append(user_prompt)`, line 1203), not via stdin the way
Cifra's default `prompt_mode="stdin"` does — the code is aware this can
fail (`except OSError as e: ... "prompt may be too large for argv"`, line
1238-1243) but the failure mode is a hard argv-length ceiling rather than
Cifra's design choice to default to stdin specifically to avoid it.

**Ollama**: substantially deeper operational tooling than Cifra currently
has — `_providers.py` includes `check_ollama_running()`,
`list_ollama_models()`, `check_ollama_model()`,
`get_ollama_model_size_estimate()` (checks local disk space against an
estimated model size before pulling), and `pull_ollama_model()` with an
`auto_confirm` flag (lines 1847-2235+). `classify(model_source="ollama")`
also gets a dedicated `ollama_two_step_classify()` path
(`text_functions.py`, referenced from `ARCHITECTURE.md`'s call-chain
diagram and confirmed present) for local models that don't reliably follow
single-shot JSON-schema instructions. Cifra's architecture document lists
"Local Inference via Ollama" only as a roadmap item (R7.1 in the landscape
doc's conclusions, not yet built) — on this specific axis CatLLM today does
meaningfully more than Cifra's current codebase.

## 6. Caching / audit log

**Finding: no result-level cache exists.** A grep for
`sqlite|diskcache|joblib|pickle.*cache|memoiz` across `cat-stack` returns
zero hits. Every "cache" hit in the codebase is either (a) HuggingFace
model-download caching for the optional embedding/formatter features
(`_embeddings.py:32-57`, `_formatter.py:200-232` — "is this multi-GB model
already on disk"), or (b) in-process, per-`UnifiedLLMClient`-instance
runtime capability flags (e.g. "does this provider reject
`response_format`," cached on `self` so a long run doesn't re-discover it
every row — `_providers.py:1350`, `1451`, `1459`, `1482`, `1571`). None of
this persists across process runs, and none of it is keyed on
(codebook/category-list + document + model) the way Cifra's SHA-256 cache
is — CatLLM has no mechanism to skip re-coding a document already processed
with the same categories and model in a prior run. This is a genuine,
verifiable gap: for a tool whose own README brags about processing
thousands of survey responses across 30+ models, having no re-run/cache
avoidance at all is a real operational cost difference, not a cosmetic one.

**Audit trail**: no `ProviderResult`-equivalent (prompt + raw response
persisted per row) was found in the engine layer — `complete()` returns a
`(response_text, error_message)` tuple (`_providers.py:1335-1336`) that
callers parse and discard; the DataFrame output includes the parsed
category flags and (for ensemble mode) `category_N_agreement` /
`category_N_resolved_by` audit columns showing *which models voted which
way and how ties were resolved* — a real and useful audit signal Cifra does
not have an equivalent to (Cifra has no multi-model ensemble mode at all)
— but not the prompt/raw-response pair itself for later inspection.

## 7. Desktop app: real, but macOS-only today

The desktop app is genuinely present in this GitHub repo — not vaporware,
not something that exists only as a claim on the website:
`app/desktop/launcher.py`, `app/desktop/catllm.spec` (a full PyInstaller
spec bundling Streamlit + the entire `cat-llm`/`cat_stack`/`cat_survey`/
`catvader`/`catademic`/`cat_cog` package tree, plus data-file/metadata
collection for `streamlit`/`altair`/`pandas`/etc.), `app/desktop/build.sh`,
and a GitHub Actions workflow (`.github/workflows/build-desktop.yml`) that
builds and optionally uploads a `.dmg` to Hugging Face on every version tag.

Architecturally it is the same "Python sidecar behind a thin shell" pattern
Cifra's own `AGENTS.md` describes as its Phase 2 plan — but the shell here
is a **local Streamlit server plus the OS default browser** (or, per
`launcher.py`'s in-process bundling logic for the frozen PyInstaller build,
a native-launched local server), not Tauri or Electron, and the UI itself
is a Streamlit app (server-rendered Python, not a React SPA).

**Platform status, confirmed by two independent primary sources**:
- `.github/workflows/build-desktop.yml`'s build matrix contains **exactly
  one target**: `macos-14` (Apple Silicon). A comment explains Intel
  (`macos-13`) was deliberately dropped from the matrix because "GitHub's
  free-tier Intel runners are scarce — jobs sit queued for hours," pending
  either a paid runner budget or a confirmed Intel user request. No Windows
  or Linux job exists anywhere in the workflow.
- `catllm.com` (fetched live) confirms this from the user-facing side:
  *"Apple Silicon builds are available below. Intel and Windows builds are
  planned."* — Apple Silicon `.dmg` (286 MB) available now; Intel Mac and
  Windows both literally labeled "Coming soon"; no Linux build mentioned at
  all on the site either.

So: CatLLM has *shipped* a real, installable, no-terminal-required desktop
app — something Cifra has not yet built (Cifra is still Phase 1, backend +
browser tab). That is a genuine lead. But it is single-platform
(Apple-Silicon-only), while Cifra's stated architecture target from day one
is cross-platform (Windows/Mac/Linux via Tauri) — the two projects are
racing toward different finish lines on this axis, not the same one, and
neither has actually reached "cross-platform desktop app" yet.

## 8. What CatLLM genuinely does better — and why it's worth taking seriously

Being fair, not just finding gaps:

1. **Multi-model ensemble consensus voting** (`classify_ensemble`,
   `consensus_threshold` — "unanimous"/"majority"/"two-thirds"/a custom
   float, `classify.py:257-285`) with an **embedding-centroid tiebreaker**
   for genuine 50/50 splits (`embedding_tiebreaker=True`,
   `classify.py:365-374`) is a real reliability mechanism Cifra has nothing
   equivalent to. Running N models and requiring agreement (with an audited
   `category_N_agreement` confidence column per row) is a defensible,
   different answer to "is this LLM coding trustworthy" than Cifra's
   single-model + post-hoc-kappa-against-gold-labels approach — arguably
   complementary, not competing: ensemble agreement is a per-row confidence
   signal available with no gold labels at all; Cifra's kappa needs a human
   gold set but measures against ground truth rather than self-consistency.
   Worth Cifra considering as an additive feature, not a replacement.
2. **The `claude-agent`/`codex-agent` SDK-based subscription path**
   (section 5) is a more robust design than raw CLI-subprocess shelling for
   exactly the problem Cifra's `CliProvider` exists to solve — structured
   rate-limit events instead of string-sniffing, explicit session sealing
   against ambient `CLAUDE.md`/project-settings leakage, and no
   argv-length ceiling. If Cifra's CLI mode keeps hitting the class of bug
   its own `AGENTS.md` had to fix once already (and CatLLM's code shows the
   same bug class independently), the `claude-agent-sdk` package (used
   directly, no need to depend on `cat-claws`) is a concrete alternative
   worth prototyping instead of hardening the subprocess path further.
3. **Ollama operational maturity** (section 5) — disk-space-aware model
   pulling, running/model-presence checks, a two-step classify path
   tailored to smaller local models' weaker instruction-following — is
   further along than anything in Cifra's current codebase, and directly
   serves Cifra's own architecture doc's unimplemented "GDPR/ethical
   compliance on sensitive texts" roadmap item.
4. **A genuinely shipped desktop app**, even if single-platform, is real
   evidence the "Python engine behind a packaged double-click app" strategy
   Cifra has also chosen is viable — a working existence proof from an
   adjacent project, for the exact packaging approach (PyInstaller sidecar)
   Cifra's own `AGENTS.md` names as its Phase 2 plan.
5. **`prompt_tune()`'s automatic per-category prompt optimization**
   (section 4/6) — while not a substitute for gold-standard validation, the
   coordinate-descent "isolate which category is wrong, ask an LLM to
   patch just that category's instruction, re-test, keep if better" loop
   is a legitimately clever idea for codebook *authoring* assistance that
   Cifra's Codebook Editor screen doesn't have any equivalent of, and could
   plausibly be adapted as an aid for researchers writing
   `definition`/`boundary_notes` text, without touching Cifra's central
   validation-against-human-gold-labels commitment.

## 9. Synthesis comparison table

| Dimension | **Cifra** | **CatLLM** (verified: `cat-stack==2.5.1` + `cat-claws==0.3.1`, GitHub commit `5481e28`) |
| :--- | :--- | :--- |
| **Where the engine actually lives** | This one repo, `src/text_as_data/` | Split across 8+ separate PyPI packages (`cat-stack`, `cat-survey`, `cat-vader`, `cat-ademic`, `cat-pol`, `cat-web`, `cat-cog`, `cat-claws`); the GitHub repo itself is a 200-line re-export shim + R/Stata wrappers + a Streamlit app |
| **Codebook abstraction** | First-class: `concept`/`description`/per-category `label`+`definition`+`positive_examples`+`negative_examples`+`boundary_notes`, YAML, compiled to a dynamic Pydantic model | **None.** `categories: list` of bare strings. `category_descriptions` exists but is wired only into the optional embedding-tiebreaker feature, never into the LLM prompt. "Codebook" is marketing language on catllm.com, not a code construct |
| **Enforced output schema** | Single-label `categoria` enum + required `justificativa` (rationale) + `trecho_evidencia` (verbatim evidence quote) | Multi-label `{"1":"0/1", "2":"0/1", ...}` indicator vector, provider-native JSON-schema/strict mode enforced. **No rationale field, no evidence-quote field** in the enforced schema |
| **Validation / gold-standard comparison** | `validation.py`: Cohen's kappa (`sklearn`), per-category precision/recall/F1, persisted mismatch list, dedicated Results/Validation screens planned | **None shipped.** `_pilot_test.py`'s `compute_metrics()` is raw accuracy/sensitivity/precision from a live interactive correction session, not a reusable gold-label comparison. Zero kappa/F1/Krippendorff code anywhere in the engine. The "88-99% agreement" figure on catllm.com is a companion research paper's benchmark result, not a software feature |
| **Reliability mechanism** | Human-gold-label kappa/F1 (needs a gold set) | Multi-model ensemble consensus voting + embedding-centroid tie-break (needs no gold set, measures self-consistency not correctness) — genuinely different and arguably complementary |
| **CLI/subscription execution** | One path: raw `subprocess` shelling to an installed CLI, best-effort JSON extraction (`CliProvider`) | Three paths: raw CLI shelling (`claude-code`, same Windows bug pattern as Cifra's *already-fixed* bug, unfixed here) **and** SDK-based (`claude-agent`/`codex-agent` via `claude_agent_sdk`/openai-codex, with rate-limit events, session sealing, no argv limit) |
| **Ollama support** | Not yet built (roadmap item) | Mature: run-check, model-list, disk-space-aware pull with confirmation, a dedicated two-step classify path for weaker local models |
| **Result caching (skip re-coding unchanged docs)** | SHA-256 of (codebook YAML + document + model) | **None.** Only HF model-download caching and in-process runtime-capability caching; no persisted result cache at all |
| **Audit trail per decision** | `ProviderResult`: exact prompt + raw pre-parse response, persisted | Ensemble mode gets `category_N_agreement`/`category_N_resolved_by` columns (a different, useful audit signal); no persisted prompt/raw-response pair found in the engine |
| **Desktop app** | Not yet built (Phase 2 plan: FastAPI + React + Tauri, cross-platform) | **Shipped today**, but Apple-Silicon-macOS-only; Streamlit + PyInstaller, not Tauri/Electron; Intel Mac and Windows both explicitly "Coming soon" on catllm.com; no Linux mentioned |
| **Language/ecosystem reach** | Python only | Python, R (8 packages, all thin wrappers over the Python engine via reticulate-style calls, not independent reimplementations), and Stata |
| **License** | Not specified in this research | GPL-3.0-or-later |
| **Domain scope** | General-purpose codebook engine (any concept/category set a researcher defines) | Domain-specific wrapper packages (survey, social media, academic, policy, web) plus an unrelated cognitive-assessment image-scoring tool (`cat-cog`) bundled into the same meta-package |

## 10. Honest final verdict

**Real overlap, but less than the surface similarity suggests.** Both
projects call themselves LLM-powered category-assignment tools for social
scientists' text, both support cloud API keys and CLI/subscription
execution and (in CatLLM's case, aspirationally in Cifra's) Ollama, and
both have a "researcher defines categories, software fills a spreadsheet"
core loop. On that surface pitch, CatLLM is a legitimate, more mature,
already-multi-language, already-desktop-shipped alternative someone
choosing a tool off GitHub search results would find first — it has more
stars-worth of engineering effort behind it (22K+ lines in the engine alone
vs. Cifra's early-stage codebase) and a working academic paper behind its
validation claims.

**But the actual differentiation Cifra is betting on — codebook-as-a-
structured-object plus mandatory rationale/evidence-per-decision plus
gold-standard statistical validation as a first-class screen — is not
something CatLLM has, and on inspection isn't something it's quietly
building either**: there is no `codebook` string anywhere in ~22,000 lines
of engine code, no kappa/F1/Krippendorff code anywhere, and the one
validation-flavored feature that exists (`prompt_tune`'s live correction
loop) explicitly optimizes the *prompt*, not the researcher's stated
operationalization, and discards the correction data rather than turning it
into a citable agreement report. This is the same "Universal Label
Failure" gap Halterman & Keith's paper (cited in Cifra's own `AGENTS.md`)
describes off-the-shelf LLM classification having — CatLLM has not built
the fix for it that Cifra is explicitly designed around. If Cifra's pitch
to a methods-conscious social scientist is "the tool that makes your
codebook's exact boundary decisions auditable and statistically validated
against your own gold-coded sample," CatLLM does not currently compete on
that specific claim, verified.

**What Cifra should concretely take from this, in priority order**:
1. Prototype the `claude_agent_sdk`-based execution path as a second
   CLI-mode implementation, not just harden `subprocess` further — it
   solves the exact class of bug Cifra already had to fix once, more
   fundamentally.
2. Consider ensemble multi-model consensus as an additive (not
   replacement) reliability signal alongside kappa-against-gold-labels —
   it's useful precisely when no gold set exists yet.
3. Prioritize Ollama support sooner rather than later given how far ahead
   CatLLM's operational tooling for it already is — this is a "catch up to
   table stakes," not a "beat them" item.
4. Do not chase CatLLM's desktop-app head start by rushing Phase 2 —
   its single-platform (Apple-Silicon-only, "coming soon" everywhere else)
   status shows shipping a *packaged* desktop app is a bigger job than it
   looks even for a much larger codebase, and Cifra's Tauri-based
   cross-platform target is a harder, more valuable goal to reach properly
   rather than to rush.
