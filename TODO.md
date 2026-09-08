# TODO

## Pending

- 2026-09-07 — After MVP handoff: durable run recovery/cancel/resume, version-scoped gold labels, complete disclosure history, CLI-command-aware cache identity, installer and a larger independent human-coded pilot remain open. See `docs/MVP_TEST_GUIDE.md`.

- 2026-09-07 — Verified alpha, not complete MVP acceptance. Priorities: cost estimate, document import UI, settings/entry point, run recovery, and version-aware scientific audit. See `docs/MVP_STATUS.md` for evidence and remaining work.

- 2026-09-03 — Product renamed Cifra → Decifra; GitHub repo is now
  `mancano-tales/decifra-text-as-data` (see `NEWS.md` for the full list of
  files touched). The local working directory on this machine still reads
  `cifra-text-as-data` on purpose — it is the hub for several active `git
  worktree` checkouts (`.claude/worktrees/multi-provider-llm-2`,
  `.claude/worktrees/v7-pipeline-tuning`, plus the external
  `cifra-text-as-data-r1.1` and `text-as-data-r24` worktrees), and
  renaming it would break their linked `.git` metadata. Once those
  worktrees are retired/merged, rename the folder to
  `decifra-text-as-data` and run `git worktree repair` (or re-add) for any
  that remain, per `docs/MULTI_AGENT_WORKTREES.md`.
- 2026-09-03 — `docs/ROADMAP.md` gained four new briefs from the CatLLM
  deep dive (`docs/research/2026-09-02_catllm_deep_dive_and_honest_comparison.md`,
  a real clone-and-read verification, not desk research): R2.8 (Claude
  Agent SDK as a second, more robust CLI-mode execution path — fixes the
  same class of Windows CLI bug Decifra already patched once, plus session
  sealing against `CLAUDE.md` leakage into extraction prompts), R2.9
  (Decifra as an MCP server, so a Claude Desktop/Claude Code session can
  drive Decifra's read operations directly — author-requested 2026-09-03,
  explicitly not a CatLLM catch-up item, Decifra-original scope), a note on
  R2.6 pointing to CatLLM's more mature Ollama tooling as an implementation
  reference, and R6.2b (multi-model ensemble consensus, distinct from
  R6.2's same-model repeat majority vote — a no-gold-set-needed reliability
  signal CatLLM has and Decifra doesn't). Author confirmed wanting both R2.8
  and R2.9 (not just one) when asked to disambiguate "MCP" from the
  Agent-SDK idea, since the two are easily conflated but solve different
  problems.
- 2026-09-02 — The post-MVP backlog now lives in `docs/ROADMAP.md`
  (self-contained task briefs R0.1 … R7.2, ordered by dependency), derived
  from the diagnosis in
  `docs/research/2026-09-02_state_of_the_project_diagnosis_and_distribution.md`.
  Pick the lowest-numbered brief whose dependencies are done; mark status
  in the ROADMAP itself. Headline items, in order: fix both READMEs (they
  describe features that do not exist); multi-variable codebooks with
  neutral English field names (before any external user has a data file);
  settings screen with persisted credentials; cost estimate before a run;
  delete endpoints; backend serving the built frontend + `cifra` entry
  point + DB in the user data dir; cancel/resume; local/OpenAI-compatible
  provider; then pilot users, then packaging (PyInstaller + pywebview
  before Tauri), then parallelism, then Krippendorff/AC1 and the other
  scientific-depth items, then the license decision.

## Prospective

- V7 pipeline tuning, items 1 and 3 remain open after
  `docs/research/2026-09-03_v7_pipeline_tuning_experiments.md`'s real
  experiments (items 2, 4, 5 resolved/measured, see Done below): (1)
  unify the enriched V7 codebooks to one language (Portuguese) — **on
  hold**, no Portuguese original exists for the hypothesis mechanism/
  premises text, author's call (2026-09-02) was to skip an unreviewed
  agent translation of ~3,500 characters of thesis content; (3) joint
  hypothesis-pair scoring (`pilot_v7.build_joint_hypothesis_messages_and_schema`)
  is implemented and measurably different from the two-blind-calls
  baseline (59.4% exact match, kappa 0.48, outside the ~31% noise floor
  measured by the reproducibility repeat) — not yet a decision about
  whether to adopt it as the default; needs more gold labels to compare
  *accuracy*, not more ablation runs, since the current V7 gold set (1-2
  usable points) has no power for that.
- Support LLM providers beyond OpenAI in `examples/` (instructor supports
  multiple providers already; the core `extraction.py` is provider-agnostic
  since it only depends on the `instructor`-patched client interface).
- Per-worktree Python virtualenv — `pip install -e .` currently repoints
  the *global* site-packages editable install to whichever checkout ran it
  last, so two sessions in two worktrees can silently clobber each other's
  `import text_as_data` target. See
  `docs/MULTI_AGENT_WORKTREES.md` § "Known friction" for the workaround
  until this is fixed properly.

## Done

- 2026-09-08 — Extended the ibis-and-page brand mark to the Quarto site
  (favicon, sidebar logo, and a separate white-on-dark navbar logo).
  Learning — a single black-on-transparent logo asset is not enough once a
  UI has both light and dark surfaces (this site's navbar is dark, its
  sidebar is light); check each surface's background before reusing one
  icon file everywhere, and crop the reference set's matching light/dark
  pair instead of only preparing one variant.
- 2026-09-08 — Replaced the emoji-style colored ibis favicon/header mark with a
  monochrome ibis-and-torn-page mark cropped from a user-supplied reference
  PNG. Learning — an agent hand-drawing brand/logo art from scratch (even
  when inspired by a reference image) produces visibly worse results than
  using the user's own generated art directly; when the user supplies
  reference images for a logo, crop/resize them, don't redraw them.
- 2026-09-07 — Added the user-requested ibis brand mark to the application header and favicon, verified in the built frontend.

- 2026-09-07 — MVP handoff: document-upload UI, OS-keyring settings, approximate pre-run token/cache estimate with optional user-supplied prices, single-origin `decifra serve`, visible evidence/audit/errors, preservation of original reviewed answers and exclusion from cache, corpus-scoped validation coverage, and SDK token recording. Frontend lint/build and the full suite passed. A three-document live CLI run started from the browser completed with all evidence verified.
- Learning — The Windows virtualenv launcher has a child Python process: a persistent server must be managed as a process tree. Approximate estimates must distinguish unknown CLI billing from zero cost, and saved defaults must load before accepting a run.

- 2026-09-07 — Consolidated V7 experiments and multi-variable design history; preserved untracked research/provider specs. Corrected both READMEs/site (R0.1), lazy database initialization and dev launchers. Verified 259 tests, frontend lint/build, HTTP workflow and one live CLI classification. See `docs/MVP_STATUS.md`.

- 2026-09-03 — V7 pipeline tuning items 2, 4, 5 measured/resolved with
  real `agy` runs against the real 16-candidate set (112 real LLM calls;
  full results and analysis in
  `docs/research/2026-09-03_v7_pipeline_tuning_experiments.md`).
  Headline: the non-discriminating-cases fix (both hypothesis sides
  scoring high at once, the pre-enrichment failure mode) holds at 0/16
  across every condition tested — robust, not fragile to persona/repeat/
  joint variations. The persona-ablation "effect" (item 4, 75% agreement
  removing the persona line) is *smaller* than the reproducibility
  repeat's own noise floor (68.8% agreement on an identical re-run) --
  at N=32 this cannot be distinguished from ordinary sampling variance,
  recorded explicitly so it isn't later cited as a clean causal effect.
  Joint scoring (item 3) diverges from baseline more than that noise
  floor (59.4%, kappa 0.48) — a real, measured effect, though whether
  it's *more accurate* needs gold labels this pilot doesn't have.
  `Codebook.build_messages`/`run_extraction` gained an `include_persona`
  toggle (default True, backward compatible) to make the ablation
  possible; `pilot_v7.build_joint_hypothesis_messages_and_schema` adds
  the joint-call prompt/schema, kept out of the general `Codebook` class
  per AGENTS.md's codebook/extraction separation rule. New
  `scripts/run_v7_tuning_experiments.py` runs all three conditions plus
  the joint condition in one process. 5 new tests (persona toggle, joint
  schema shape) plus the delimiter tests from item 2.
- 2026-09-02 — Slice 4, Validation screen: closes the last unbuilt
  screen from `AGENTS.md`'s original MVP list — every one of the 5
  screens now exists. `POST /runs/{run_id}/gold-labels` (CSV upload
  shaped like the results export plus a `gold_categoria` column, blank
  cells skipped, any non-blank value not a real codebook category
  rejects the whole upload with every bad row listed) and
  `GET /runs/{run_id}/validation` (coverage, per-category
  accuracy/kappa/precision/recall/F1 via `agreement_report()`, a
  disagreement list with the same `document_snippet` convention as
  results). A document with more than one gold row (e.g. a QualiLab
  "individual"-layer import) is excluded from the report and counted,
  never silently resolved to one value. Frontend: `ValidationPanel.tsx`,
  composed into `ResultsTable.tsx` below the existing results table
  (not a separate tab — a validation report only makes sense in the
  context of one specific run). Re-uploading gold labels for an
  already-labeled document replaces the prior manual row instead of
  appending a second one, so correcting a typo doesn't get
  misinterpreted as a second coder and excluded — the same class of bug
  the round-2 red-team review fixed on the QualiLab gold-label import
  path a few hours earlier, applied here to the plain-CSV path before
  it could ship with the same gap. 18 new backend tests (12 planned +
  6 added: missing-columns, non-integer document_id, reimport-replaces,
  empty-report-before-any-labels), 238/238 passing (now 238 total after
  landing alongside the git-safety work below). Manually verified
  end-to-end in a real browser against real run data (not just curl):
  export → edit → re-upload → report renders with correct coverage/
  metrics/disagreements, confirmed in both PT and EN. Implements
  `docs/superpowers/specs/2026-09-02-slice-4-validation-screen-design.md`
  and `docs/superpowers/plans/2026-09-02-slice-4-validation-screen.md`
  (adapted from the plan's assumed `HumanLabelRecord` shape, written
  before QualiLab interop landed, to the real one — a `layer` field the
  plan didn't know about, which defaults correctly to `"final"` for a
  manual CSV upload).

- 2026-09-02 — Git-safety governance for the shared multi-agent working
  directory, in response to a real incident (a `git checkout --orphan` +
  `git clean -fdx` switched HEAD for all four sessions sharing one
  directory and destroyed another session's uncommitted work). Two layers:
  (1) `docs/MULTI_AGENT_WORKTREES.md` — the actual fix, documenting
  `git worktree` per session, referenced from `AGENTS.md`'s rules section;
  (2) `tools/guard_git_command.py`/`.sh` + `.claude/settings.json`'s
  `PreToolUse` hook — defense-in-depth, a hardened port of
  `agentic-workflow-template`'s guard, with every bug a 3-model red-team
  review (claude-sonnet-4-6, gemini-3.7-flash-high, gemini-3.1-pro-high
  via `agy`) found in the original fixed: parser desync on an unrecognized
  global flag, fragile `&&`/`||` handling, `sh -c`/`eval` command hiding,
  `git config alias.*` subcommand-name bypass, `symbolic-ref`/`update-ref`
  moving HEAD without "checkout", `stash drop`/`clear`, and glob/directory
  paths bypassing the exact-`.`-only restore/checkout check. Branch
  switches are context-aware (free inside a worktree, require an explicit
  `CIFRA_CONFIRM_SHARED_HEAD_SWITCH=1` prefix in the shared main
  directory) rather than a blanket block, since all three models agreed
  that would cripple legitimate work. Full investigation and the red-team
  findings in detail:
  `docs/research/2026-09-02_git_safety_governance_for_shared_agent_working_directory.md`.
  45 new unit tests against the guard's `check_command()` directly,
  including a replay of the actual incident's two commands confirming the
  first (the branch switch) is now caught, which the original guard would
  have missed. Verified live through the real `PreToolUse` mechanism, not
  just unit tests: a real Bash tool call was intercepted and blocked by
  Claude Code itself. 238/238 tests passing.

- 2026-09-02 — Reproducibility verification (DAAF-inspired prospective
  item): `GET /runs/{run_id}/reproducibility?compare_to={other_run_id}`
  compares two runs sharing the same codebook/corpus/model and reports
  whether the LLM's own output is stable — not correctness against gold,
  just self-agreement. Reuses `agreement_report()` via a thin
  `reproducibility_report()` relabeling wrapper (`validation.py`) rather
  than new statistics code. Design-shaping discovery made along the way:
  `run_extraction` caches by `(document, codebook_hash, model)`, so a
  naive "run it again" would just replay the first run's cached answers —
  `RunRecord` gained a persisted `bypass_cache` flag (persisted, not a
  request-only parameter, since `run_extraction` runs as a disconnected
  background task) to force a real second call to the provider. 6 new
  tests, including one asserting the provider is actually called twice
  when `bypass_cache=true` and only once when it's the default `false`.
  Landed the same session as a peer's round-2 red-team pass on
  `corpus_import.py`/`export.py`/`qualilab_interop.py` in this same
  shared working directory — coordinated live (both sessions confirmed
  exact line ranges before either touched `app.py`) to land without
  overlapping edits; see commit `08693c7`'s message for the split.
- 2026-09-02 — TXT/MD/DOCX/PDF corpus import (Slice 2 covered
  CSV/XLSX/pasted text only): `POST /corpora/documents`, a multi-file
  upload where each file is one document (unlike CSV/XLSX's one-row-is-
  one-document) — a mixed batch of file types in one request is fine,
  dispatched per file by extension. New `corpus_import.py` parsers:
  `parse_txt_bytes` (also runs `ftfy.fix_text()`, already a dependency
  for exactly the mojibake class of bug AGENTS.md's V7 pilot notes
  describe), `parse_docx_bytes` (paragraphs, then table cells --
  `python-docx`), `parse_pdf_bytes` (page by page, no OCR — scanned/
  image-only PDFs are explicitly out of scope per AGENTS.md). All-or-
  nothing on a bad file in a batch, matching the CSV/XLSX endpoints'
  existing convention. `python-docx`/`pypdf` added to `pyproject.toml`
  (were already present in the dev environment but undeclared). 12 new
  tests, including a hand-built minimal-but-valid PDF (correct xref
  table and all) so PDF extraction is tested for real rather than mocked.
- 2026-09-02 — QualiLab interoperability: `POST /corpora/import-qualilab`
  (import a `.qualilab` project's documents as a corpus, preserving
  QualiLab's own doc id as the new `DocumentRecord.external_id`),
  `POST /corpora/{corpus_id}/import-qualilab-labels` (map `doc_values` to
  `HumanLabelRecord` gold labels via a required, explicit
  `value_mapping` — all-or-nothing on mapping validity, reports
  `coverage` for documents with no recorded value), and
  `POST /runs/{run_id}/export-qualilab` (inject a run's extractions back
  into a freshly re-uploaded `.qualilab` file as new `doc_values`, never
  a cached copy — matches by `external_id`, upserts by a deterministic id
  so re-exporting the same run doesn't duplicate). New
  `qualilab_interop.py` module (`open_qualilab_project`,
  `qualilab_documents_to_records`, `qualilab_doc_values_to_human_labels`,
  `inject_extractions_into_qualilab`, `serialize_qualilab_project`).
  New `HumanLabelRecord` table, deliberately multi-row per document (see
  the Validation screen note above for how that interacts with
  `agreement_report()`). Implements
  `docs/superpowers/specs/2026-09-02-qualilab-interop-design.md`
  (revision 4, 18 numbered findings across 3 red-team rounds) as written,
  including its two hardest-won details: the zip-bomb guard via
  `ZipInfo.file_size` checked before any `read()`, and the upsert-not-
  append fix for finding #13 (three independent reviewers across two
  model families caught that an earlier revision's "idempotent re-export"
  claim wasn't actually implemented). Tested against a copy of QualiLab's
  own shipped example fixture (`tests/fixtures/`, MIT), not synthetic
  mocks, for every behavior where the real file's shape matters — this is
  what caught the real "final" vs. "individual" layer counts used in the
  test assertions. 26 new tests, 126/126 passing (pilot_v7's CLI-dependent
  tests excluded from that count, unaffected).

- 2026-09-02 — CI: `.github/workflows/ci.yml`, two jobs on every push and
  every PR into main — `backend` (Python 3.12, `pip install -e ".[dev]"`,
  `pytest -q`) and `frontend` (Node 20, `npm ci`, `npm run lint`,
  `npm run build` — the latter runs `tsc -b` too, so a type error fails CI
  even though `oxlint` alone wouldn't catch it). Coordinated with the two
  other active sessions (`text-as-data-6d`, `text-as-data-8a`) before
  picking this up, to confirm it didn't collide with the Validation screen
  or QualiLab interop work in flight — this was the one item both agreed
  was fully unclaimed. Verified both jobs' exact commands pass locally
  before committing (109 tests green; frontend lint clean aside from 3
  pre-existing non-blocking `set-state-in-effect` warnings; build
  succeeds) rather than trusting the YAML would work once pushed.
- 2026-09-02 — GUIDE-LLM-shaped AI-use disclosure report per run
  (`GET /runs/{id}/disclosure`), adopted after studying the DAAF framework
  (`DAAF-Contribution-Community/daaf`) for lessons applicable to Decifra. New
  `disclosure.py` maps the real GUIDE-LLM checklist (13 items across
  sections A-G, fetched from the actual checklist page rather than
  guessed — llm-checklist.com/checklist) onto what Decifra already records
  per run: model/provider/access-mode (`RunRecord` gained `provider_mode`/
  `provider_detail`, persisted at creation instead of only living
  transiently on `CreateRunRequest`), the exact prompt sent per document
  (already-existing `prompt_sent`), whether output is validated against
  human gold labels (honestly reports "not yet" — no `human_labels` table
  exists yet), and reproducibility pointers (codebook id, run id, git
  commit). Doubles as the "citation propagation" idea from the same
  research: rather than a separate references subsystem, provenance and
  disclosure are the same report. Explicitly out of scope from that same
  research pass: DAAF's Reproducibility Verification mode (see Prospective
  below) and the rest of DAAF's much larger surface (9 engagement modes,
  benchmarking, etc.) — this took the 1-2 cheap, high-value ideas, not the
  whole framework. Also formalized the ad hoc "write down what surprised
  us" pattern this file was already doing as a named convention
  (`AGENTS.md` § `LEARNINGS.md`).
  Fell out of this work: closed the recurring schema-drift TODO below by
  building it instead of writing it up again — `db.py`'s `get_engine()`
  now runs an additive `_ensure_columns()` migration on every startup
  (diffs `PRAGMA table_info` against the SQLModel schema, `ALTER TABLE
  ADD COLUMN` for anything missing, defaulted and additive-only — never
  drops or renames), so a column added to a model doesn't require anyone
  to remember to patch whichever `codifica.sqlite` happens to be live.
  6 new tests (2 migration, 4 disclosure) plus coverage on the new
  endpoint; 99/99 passing (pilot_v7's CLI-dependent tests excluded from
  this count, unaffected by this change).
- 2026-09-02 — Full prompt/response audit trail, prompted by the author
  asking how to verify a shown prompt wasn't invented after the fact and
  whether the pipeline is reproducible. `providers.py` gained
  `ProviderResult(parsed, prompt, raw_response)`; both `ApiKeyProvider` and
  `CliProvider` return one instead of a bare parsed model.
  `ExtractionRecord` gained `prompt_sent`/`raw_response` columns, persisted
  by `run_extraction` on every row (copied from the cached record on a
  cache hit; best-effort `json.dumps(messages)` fallback if the provider
  itself fails after `build_messages` succeeded). Both fields now flow
  through `GET /runs/{id}/results` and every export format automatically,
  since `app.py` already builds those rows via `ExtractionRecord.model_dump()`.
  8 new tests, 95/95 passing. Full methodology and the reproducibility
  test that motivated it (a same-prompt repeat run on the V7 candidates:
  21/32 exact match, one real 3-step reversal inspected and found to
  reflect genuine evidence ambiguity, not model incoherence) written up in
  `docs/research/2026-09-02_llm_pipeline_verification_methodology.md`.
- 2026-09-02 — Enriched the V7 Bayesian pilot codebooks and confirmed the
  fix with real data: added `HYPOTHESIS_DEFINITIONS` (full mechanism +
  premises per side, not just the hypothesis name) and
  `PROBABILITY_BOUNDARY_NOTES` (scope-check / discriminating-power /
  consistency instructions per category) to `pilot_v7.py`
  (`build_enriched_hypothesis_codebook_spec`), then re-ran the identical
  16 evaluations through the identical `agy`/Gemini with nothing else
  changed. Non-discriminating cases (both sides of a pair scored
  `muito_provavel`) went from 6/16 to 0/16; the `muito_provavel` bias
  dropped from 66% to 28% of outputs; the flagged scope-condition failure
  (H3a scored `muito_provavel` for a left-wing government's policy)
  flipped to `quase_impossivel`, with the model's own justification now
  naming the governing party and calling it a "hoop test failure" in
  Fairfield & Charman's own terms. Confirms the author's diagnosis: this
  was a codebook-specification gap, not a model/provider reliability
  problem — see the project memory note on diagnosing prompt before model
  for the durable lesson. Every spreadsheet export from this pilot
  (`scripts/run_v7_candidates_via_agy.py`) now also carries the complete
  hypothesis definition and complete evidence text per row, not just a
  short justificativa, per the author's explicit requirement.
- 2026-09-02 — Slice 3, Runs + Results screen: a "Runs" tab (list +
  detail: create a run in API-key or CLI mode, live progress polling,
  results table with category filter, inline categoria/justificativa
  edit, CSV/XLSX/JSON export). New backend: `GET /runs`,
  `PUT /runs/{id}/results/{id}`, `GET /runs/{id}/export`, and
  `GET /runs/{id}/results` now includes a `document_snippet`. Also fixed
  CORS to allow any localhost port instead of a single hardcoded
  `:5173` origin — hit as a real bug running two frontends against one
  backend during verification, not a hypothetical. Screen 5 (Validation)
  remains a separate, unstarted slice. Design:
  `docs/superpowers/specs/2026-09-01-slice-3-runs-results-screen-design.md`;
  plan: `docs/superpowers/plans/2026-09-01-slice-3-runs-results-screen.md`.
- 2026-09-01 — Slice 2, Corpus import + Codebook editor screens: first
  frontend (Vite+React+TypeScript) talking to new `/corpora/*` and
  `/codebooks/*` FastAPI endpoints. Corpus import covers CSV/XLSX/pasted
  text (TXT/DOCX/PDF deferred). Codebook editor is a structured form
  (concept, categories with definitions/examples/boundary notes) with a
  YAML preview reusing `codebook.py`'s own format via a shared
  `validate_spec`/`spec_to_yaml_string`. Screens 3-5 (Run, Results,
  Validation) remain curl/API-only, deferred to Slice 3 per
  `AGENTS.md` § "Build order for the MVP". Design:
  `docs/superpowers/specs/2026-09-01-slice-2-corpus-codebook-screens-design.md`.
- 2026-09-01 — Slice 1, thin backend skeleton: FastAPI + SQLite backend
  verified end-to-end via `curl` against real V7 pilot data using CLI mode
  (`claude -p`, no API key available); both hypothesis sides ran
  successfully but disagreed with gold (`cinquenta_e_cinquenta` predicted
  vs. `provavel` gold on both, 0/2) — see `AGENTS.md` § "Build order for
  the MVP" for full outcome and two Windows-specific `CliProvider` bugs
  found along the way.
- 2026-08-30 — Initial scaffold (codebook/extraction/validation modules,
  toy example, tests). Agent: Claude Sonnet 5 (Claude Code).
