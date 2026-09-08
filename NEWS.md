# NEWS

## 2026-09-07 (brand)

- Replaced the placeholder letter and default Vite favicon with an original emoji-style ibis mark: ivory body, curved dark bill, warm legs and a blue background. The same scalable SVG serves the header and browser tab.

## 2026-09-07 (MVP handoff)

- Added document-file import UI, persisted provider defaults and OS-keyring credentials, approximate token/cache estimates, optional user-entered prices, and a single-server CLI with a built frontend.
- Exposed evidence and prompt/response records, highlighted per-document errors, preserved pre-review answers and excluded reviewed rows from automatic cache. Scoped validation coverage to the current corpus and recorded SDK-reported token usage.
- Verified the full suite and production frontend build; three synthetic documents classified through the real CLI from the browser, with verified evidence in all three. See `docs/MVP_TEST_GUIDE.md` for handoff and limits.

## 2026-09-07

- Consolidated outstanding experiment/design history and preserved local research specs. Corrected alpha/MVP claims in both READMEs and the site; documented measured checks and gaps in `docs/MVP_STATUS.md`.
- Removed database writes at app import and serialized lazy initialization; added regression coverage. Repaired development environment/port selection and Windows process cleanup. Full suite: 259 passed; frontend lint/build passed with three existing warnings; HTTP and live CLI smoke checks passed.
- Learning: use isolated temporary directories and distinguish authentication/sandbox failures from product failures. A successful synthetic classification is not a scientific accuracy estimate.

## 2026-09-03 (1)

- Product renamed from **Cifra** to **Decifra** (author decision), because
  "Cifra" collided informally with unrelated existing brands; "Decifra"
  keeps the same encoding/decoding metaphor. The author renamed the GitHub
  repository itself this time (`mancano-tales/decifra-text-as-data`,
  `origin` updated to match) — unlike the earlier Codifica→Cifra rename,
  which stayed a documentation-only change. Branding updated across both
  READMEs, `AGENTS.md`'s Product Vision, the FastAPI app title, the
  `X-Cifra-Matched-Count`/`X-Cifra-Skipped-Count` QualiLab-export response
  headers (now `X-Decifra-*`, with matching test updates), the
  `disclosure.py` report text, the frontend page title and locale strings
  (both `en.json` and `pt-BR.json`), the dev-server startup banners
  (`scripts/dev.sh`/`dev.ps1`), `SECURITY.md`, the Quarto site
  (`site/_quarto.yml` and pages, including GitHub/Pages URLs), and
  `docs/MULTI_AGENT_WORKTREES.md`. Also updated the GitHub repo's
  description to a bilingual EN/PT-BR one-liner. Deliberately **not**
  renamed: dated snapshot docs (`docs/research/2026-*.md`, older `NEWS.md`
  entries, plans under `docs/superpowers/plans/`, the dated
  `docs/research/materials.md`) — left as historical record of what the
  product was called when each was written, same treatment the "Codifica"
  placeholder already gets. Also **not** renamed: the local working
  directory (`cifra-text-as-data`), because it is the hub for several
  active `git worktree` checkouts and renaming it would break their linked
  `.git` metadata — see `AGENTS.md`'s Product Vision intro for the
  reasoning and `docs/MULTI_AGENT_WORKTREES.md` for the worktree layout.

## 2026-09-02 (7)

- Strategy pass after the MVP closed: a full read of the repository
  (governance files, all 116 commits, every backend module and frontend
  component, specs/plans, research reports; suite re-run, 238 passing but
  only with `PYTHONPATH=src`, because the global editable install points
  at a deleted worktree) written up as
  `docs/research/2026-09-02_state_of_the_project_diagnosis_and_distribution.md`.
  Records the author's reframing of Cifra as general-purpose software,
  what is right (the auditable pipeline exists end to end; the V7
  codebook-enrichment result is the product's thesis demonstrated), where
  it drifted (single-variable codebook with Portuguese field names
  hardcoded across engine/DB/frontend; credentials only via env var; no
  cost estimate; sequential, uncancellable, unrecoverable jobs; no delete;
  backend does not serve the frontend; Anthropic/OpenAI only; a specific
  study inside the product package; both READMEs describing features that
  do not exist), a cost comparison of distribution paths (recommends
  pipx/uv install first, then PyInstaller + pywebview, Tauri only if that
  proves insufficient, and budgeting code signing now), a build order, and
  trajectory risks. The diagnosis is turned into `docs/ROADMAP.md`: task
  briefs R0.1 … R7.2 written to be handed to a fresh agent session with no
  other context, each with dependencies, size, whether a spec is required
  first, and acceptance criteria. `TODO.md` Pending now points there.

## 2026-09-02 (6)

- Slice 4, Validation screen — the last unbuilt screen from `AGENTS.md`'s
  original MVP list. Every one of the 5 screens now exists.
  `POST /runs/{run_id}/gold-labels` accepts a CSV shaped like the results
  export plus a `gold_categoria` column (blank cells skipped as "not yet
  reviewed"; any non-blank value that isn't a real codebook category
  rejects the whole upload with every bad row listed, not just the
  first). `GET /runs/{run_id}/validation` reports coverage, per-category
  accuracy/kappa/precision/recall/F1 (via the `agreement_report()`
  function CI/round-2 already exercise), and a disagreement list. A
  document with more than one gold row — e.g. a QualiLab
  "individual"-layer multi-coder import — is excluded from the report
  and counted, never silently resolved to one value on the researcher's
  behalf. `ValidationPanel.tsx` renders below the existing results table
  in the Runs screen rather than as a separate tab, since a validation
  report only makes sense in the context of one specific run's own
  predictions.
  Re-uploading gold labels for a document already manually labeled
  replaces the prior row instead of appending a second one — without
  this, correcting a typo in a re-upload would create what looks like a
  second coder and get the document wrongly excluded as multi-coder.
  This is the identical bug class the round-2 red-team review fixed
  hours earlier on the QualiLab gold-label import path (see (2) below);
  applying the same fix here, before shipping, meant Slice 4 never
  shipped with the gap in the first place.
  Implemented from a spec/plan written and committed by an earlier
  session, adapted where the real landed `HumanLabelRecord` (a `layer`
  field the plan pre-dated) differed from what the plan assumed.
  18 new backend tests (12 from the plan, 6 added), 238/238 passing.
  Manually verified end-to-end against real run data in an actual
  browser (not just curl): started both dev servers, opened a real run
  with 26 documents, exported its results, built a small gold-label CSV
  by hand (one row agreeing with the model, one disagreeing), uploaded
  it through the real form flow, and confirmed the coverage line,
  per-category metrics table, and disagreement list all rendered
  correctly with the real numbers — then re-confirmed the same in
  English via the language toggle.

## 2026-09-02 (5)

- Git-safety governance for the shared multi-agent working directory,
  after a real incident: a `git checkout --orphan` + `git clean -fdx`
  switched HEAD for all four Claude Code sessions sharing this repo's one
  physical working directory at once, and destroyed another session's
  uncommitted work. Rather than shipping the first fix that came to mind,
  the resulting plan was red-teamed by three independent models
  (claude-sonnet-4-6, gemini-3.7-flash-high, gemini-3.1-pro-high, via
  `agy`) before any code changed — all three, independently, traced the
  incident's own first command through the proposed guard and found it
  would NOT have been blocked, and converged on the same diagnosis: a
  shared HEAD/index/working-tree across agents is the actual defect, not
  an insufficiently large command blocklist. Shipped two layers: (1)
  `docs/MULTI_AGENT_WORKTREES.md`, documenting `git worktree` per session
  as the real fix, referenced from `AGENTS.md`; (2) a hardened
  `PreToolUse` hook (`tools/guard_git_command.py`/`.sh` +
  `.claude/settings.json`) as honestly-scoped defense-in-depth, fixing
  every concrete bug the red-team found in the source template it was
  ported from (parser desync on unrecognized global flags, fragile
  `&&`/`||` handling, `sh -c`/`eval` bypass, a `git config alias.*`
  subcommand-shadowing bypass found by only one of the three models,
  direct-ref-write HEAD moves, `stash drop`/`clear`, glob/directory
  restore paths). Branch switches are worktree-aware rather than blanket-
  blocked. Full investigation, the three critiques in detail, and the
  cross-model convergence/divergence analysis:
  `docs/research/2026-09-02_git_safety_governance_for_shared_agent_working_directory.md`.
  45 new tests against the guard directly (including a replay of the
  actual incident, confirming the fix catches what the original wouldn't
  have), verified live through the real `PreToolUse` mechanism, not just
  unit tests. 238/238 passing.

## 2026-09-02 (4)

- CI added: `.github/workflows/ci.yml` runs `pytest` (backend) and
  `oxlint` + `tsc -b`/`vite build` (frontend) on every push and every PR
  into main. Closes the last item from the original "CI (lint + test on
  push) — not set up yet" TODO note. Picked after checking in with the
  two other sessions active on this repo today (`text-as-data-6d` on the
  Validation screen, `text-as-data-8a` on QualiLab interop) to confirm it
  was genuinely unclaimed and collision-free — the author asked for that
  coordination explicitly before starting.

## 2026-09-02 (3)

- Red-teamed Slice 3 with two independent `agy`-driven adversarial reviews
  (one against the new backend endpoints/export.py, one against
  RunForm/ResultsTable/RunsPage), each in read-only mode against the real
  code, not a description of it. Verified every claim empirically before
  acting — one report's "double `\r\n`" CSV bug turned out to be false
  (`io.StringIO` doesn't do the OS-level newline translation `open()`
  does), and a "500 crash if a run's codebook is deleted" report was
  correct about the crash but wrong that it's reachable: the FK
  constraint on `runs.codebook_id` already blocks that delete, confirmed
  by trying it and watching SQLite refuse. Fixed what was real: CSV
  injection (CWE-1236, a `justificativa` or document text starting with
  `=`/`+`/`-`/`@` would execute as a formula in Excel) and an XLSX export
  crash on control characters (reproduced with a literal `\x0b`) in
  `export.py`; an N+1 query fetching one document per result row in
  `GET /runs/{id}/results`/export, batched into one query; WAL journal
  mode for the SQLite engine, since multiple concurrent sessions writing
  to one shared `codifica.sqlite` turned out to be today's actual usage
  pattern, not a hypothetical; and three frontend races in
  `RunsPage.tsx`/`ResultsTable.tsx`/`RunForm.tsx` — a leaked polling
  interval and a stale-response race from switching runs quickly (fixed
  with one selection-token mechanism), a concurrent-edit save clobbering
  a different row's in-progress edit, and an unhandled promise rejection
  when a post-creation refresh failed. Also hit and fixed, along the way,
  the second occurrence of the "SQLite doesn't auto-migrate" gap
  (`extractions` was missing the `prompt_sent`/`raw_response` columns
  another session had added to the model, 500ing `GET /runs` on the
  shared `codifica.sqlite`) with an additive `ALTER TABLE`, after
  confirming with the user before writing to shared state — see TODO.md
  for the durable note on adding real migration tooling.

## 2026-09-02 (2)

- Every LLM extraction is now auditable: `ExtractionRecord` persists the
  exact prompt sent and the raw (pre-parsing) response received, not just
  the parsed categoria/justificativa/trecho_evidencia. Prompted by the
  author asking, about a prompt shown for the V7 pilot, how to verify it
  wasn't reconstructed after the fact and whether the pipeline is even
  reproducible — the honest answer was that `CliProvider` built and
  discarded the final prompt without ever persisting it. `providers.py`
  gained `ProviderResult(parsed, prompt, raw_response)`, returned by both
  `ApiKeyProvider` and `CliProvider` instead of a bare parsed model; both
  new `ExtractionRecord` fields flow automatically through
  `GET /runs/{id}/results` and every export format, since those already
  build rows via `model_dump()`. Also ran a real reproducibility test
  (re-running the 16 V7 candidates through the identical enriched
  codebooks a second time): 21/32 (66%) exact match, 9 of the 11
  differences one step apart on the 7-point scale, one real 3-step
  reversal whose two justificativas were read side by side and found to
  be two defensible readings of genuinely ambiguous evidence, not model
  incoherence. Full verification methodology (a reusable 4-step procedure:
  reconstruct from the persisted DB record, prove determinism by
  byte-comparing against fresh source, trace prompt provenance via git
  blame, test reproducibility empirically) and findings — including an
  unresolved language-mixing issue introduced while enriching the
  codebooks, and a structural note that hypothesis-pair sides are scored
  in separate, mutually-blind LLM calls — written up in
  `docs/research/2026-09-02_llm_pipeline_verification_methodology.md`.
  8 new tests, 95/95 passing.

## 2026-09-02

- Slice 3 shipped: a "Runs" tab joins Corpus and Codebook — create a run
  (API-key or CLI provider mode, including a CLI prompt-delivery choice
  for CLIs like `agy` that take the prompt as an argument rather than
  stdin), watch it progress live via 2-second polling, then browse its
  results in a table with a category filter, inline
  categoria/justificativa editing (validated against the run's own
  codebook labels — an edit to a category the codebook doesn't define is
  rejected), and CSV/XLSX/JSON export. New backend: `GET /runs` (list),
  `PUT /runs/{id}/results/{id}` (edit), `GET /runs/{id}/export`, and
  `GET /runs/{id}/results` now joins in a `document_snippet` so a result
  row is legible without a separate corpus lookup. Verified end to end in
  a real browser: created a live run against `claude -p`, watched it
  transition from progress bar to results table with no manual reload,
  edited a row and confirmed it persisted after navigating away and back,
  downloaded and parsed all three export formats. Also fixed a real CORS
  bug hit during that verification — the backend only ever allowed
  `http://localhost:5173`, which breaks the moment two dev frontends run
  on different ports (exactly what happened, with two Claude Code
  sessions working this repo concurrently); now allows any
  localhost/127.0.0.1 port via `allow_origin_regex`, appropriate since
  this backend has no production deployment to restrict against. Screen 5
  (Validation) is the only screen from `AGENTS.md`'s original MVP list
  left unbuilt. Design:
  `docs/superpowers/specs/2026-09-01-slice-3-runs-results-screen-design.md`;
  plan: `docs/superpowers/plans/2026-09-01-slice-3-runs-results-screen.md`.

## 2026-09-01 (3)

- `POST /runs` can now actually select CLI mode, not just API-key mode.
  Slice 1's `CreateRunRequest`/`get_provider_dependency` only ever built an
  `ApiKeyProvider(vendor="anthropic")` — the agent-agnostic CLI path was
  real in `providers.py` (exercised once via an ad hoc worktree script for
  Task 10's `claude -p` verification run) but never reachable through the
  actual REST API. Added `provider_mode` ("api_key" | "cli"),
  `cli_command`, and `cli_prompt_mode` to `CreateRunRequest`; `provider_mode
  = "cli"` now builds a real `CliProvider` from the request's own command.
  Also extended `CliProvider` itself with `prompt_mode="arg"`: Google
  Antigravity's CLI (`agy -p "<prompt>"`) takes the prompt as a trailing
  argument and errors "flag needs an argument" if none is given, unlike
  `claude -p`, which blocks reading it from stdin — the existing
  stdin-only design silently couldn't drive `agy` at all. 71/71 tests
  pass (4 new: 2 for `CliProvider`'s new `prompt_mode`, 2 for
  `get_provider_dependency`'s new CLI branch).

## 2026-09-01 (2)

- Slice 2 shipped: the backend gets its first frontend. A new `frontend/`
  Vite + React + TypeScript SPA talks to the FastAPI backend over `fetch`
  (CORS enabled for the Vite dev origin) and adds two screens: **Corpus**
  (paste text, or upload a CSV/XLSX and pick which column is the
  document text — TXT/DOCX/PDF import stays deferred) and **Codebook**
  (a structured form for concept/categories/examples/boundary notes,
  with a YAML preview generated by the same `codebook.py` engine the
  backend uses to run extractions, via a new shared
  `validate_spec`/`spec_to_yaml_string` pair so the YAML file format and
  the editor's JSON API can never validate differently). New backend
  endpoints: `POST/GET /corpora`, `POST/GET/PUT /codebooks`. A design
  decision made mid-implementation: corpora are *not* a new SQLite
  table — `corpus_id` stays the plain string it already was in Slice 1,
  and `GET /corpora` derives its listing by grouping `documents`, to
  avoid a breaking migration for referential integrity this slice
  doesn't need. Verified manually in a real browser against a live
  backend (paste-corpus and full codebook create/reload round-trip); all
  67 backend `pytest` tests pass. Run/Results/Validation screens (Screens
  3-5) remain curl/API-only, deferred to Slice 3. Design:
  `docs/superpowers/specs/2026-09-01-slice-2-corpus-codebook-screens-design.md`;
  plan: `docs/superpowers/plans/2026-09-01-slice-2-corpus-codebook-screens.md`.

## 2026-09-01

- Research dialogue report created in `docs/research/2026-09-01_halterman_keith_codebook_llms_dialogue_and_cifra.md` analyzing Halterman & Keith's (2025) foundational paper "Codebook LLMs: Evaluating LLMs as Measurement Tools for Political Science Concepts" (arXiv:2407.10747v2).
  Establishes how Cifra (`cifra-text-as-data`) implements their five-stage measurement framework (Stage 0 YAML codebooks, Stage 1 label-free behavioral tests, Stage 2 zero-shot evaluation, Stage 3 error analysis, Stage 4 QLoRA instruction tuning) and extends it via auditable structured schemas (`rationale` + `evidence_span`), dual provider engines, and SQLite WAL local storage.

- Product journal entry: Analyzed the 9-page research paper "O Banco de Dados da Luta pela Terra (DATALUTA)..." (NERA/UNESP, 2025/2026).
  Recorded research report in `docs/research/2026-09-01_dataluta_paper_analysis_and_cifra_synergy.md`.
  Findings: The DATALUTA paper uses BeautifulSoup for metadata, SpaCy NER + RAG for IBGE municipality lookup, and fine-tuned BERTimbau-large for UN SDGs. It achieves only ~50% precision on complex interpretative fields ("Action Purpose"). Cifra (`cifra-text-as-data`) solves this bottleneck using instruction-following YAML codebooks (boundary notes, few-shot examples, rationale, evidence spans) and provides inter-coder agreement validation against DATALUTA's 2021–2023 historical human gold-standard labels.
- Package and repository name updated to **`cifra-text-as-data`** (`pyproject.toml`, `AGENTS.md`, `README.md`).
- Working product name officially changed from "Codifica" to **"Cifra"**.

## 2026-08-31 (2)

- Both open items from the first 2026-08-31 entry resolved: the LLM
  provider layer is agent-agnostic (CLI mode — Claude Code CLI, Codex CLI,
  or a generic command adapter, best-effort JSON — alongside the existing
  API-key/`instructor` mode as the reliable path); and the real pilot data
  is the `Reforming-TE-PT` Bayesian process-tracing workbook ("V7"),
  chosen over the simpler Folha relevance-triage pipeline in
  `Mancano2026-MA-Thesis`. Located, inspected read-only (with explicit
  root-plan authorization), and found to have only 7 fully human-coded
  rows (5 with justification) — small but real; proceeding with it for
  Slice 1 anyway, on the author's call. Also found: text mojibake in the
  evidence content (fix before use) and an old/new hypothesis-group naming
  inconsistency in the coded rows. Full detail in `AGENTS.md` §
  "Real-world pilot data".

## 2026-08-31

- `AGENTS.md` expanded with the full product vision for evolving this
  library scaffold into "Codifica", a local-first app for LLM-assisted
  text coding with a codebook editor, run queue, results table, and a
  validation screen (Cohen's kappa + disagreement review) against
  human-coded gold labels. Architecture closed: Python/FastAPI backend now
  ("sidecar-ready" from commit 1), Tauri+PyInstaller packaging later, no
  rewrite. Build order agreed via brainstorming: a thin backend-only
  skeleton (Slice 1, reusing the existing `policy_stance` toy example)
  before any of the 5 MVP screens are built individually. Two things
  still open: the LLM provider layer (must support both a CLI the user
  already has a subscription for, and a direct API key) and whether/how
  to bring in real pilot data from `Mancano2026-MA-Thesis` ("V7" coding
  spreadsheet) and `folha-scraper` — both live in sibling repositories and
  need a root-level plan before anything is touched there.

## 2026-08-30

- Initial scaffold: `codebook`, `extraction`, `validation` modules, a toy
  end-to-end example, and a test suite exercising the pipeline against a
  fake LLM client. No real domain codebook yet — see `TODO.md`.
