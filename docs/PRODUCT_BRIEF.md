# Decifra — original product brief

> **Moved from `AGENTS.md` on 2026-09-26, verbatim** (headings unchanged, so older references
> to "`AGENTS.md` § …" resolve here). This is the author's brief agreed on 2026-08-31 plus
> the dated updates made to it until 2026-09-02. Its **architecture decisions still hold**;
> its status notes (slices, test counts, pilot numbers) are dated. Current state:
> [`MVP_STATUS.md`](MVP_STATUS.md) and [`ROADMAP.md`](ROADMAP.md); where a later spec under
> `superpowers/specs/` differs from this brief, the spec wins.

## Product Vision — What This Is Becoming

> This section captures the author's brief for evolving the current
> library scaffold into a full application, agreed 2026-08-31. It is the
> source of truth for scope and architecture until superseded by a dated
> update to this section. Working product name: **"Decifra"** (renamed
> 2026-09-03, superseding "Cifra", which itself superseded the earlier
> "Codifica" placeholder — "Cifra" collided informally with unrelated
> existing brands; "Decifra" ["to decipher"] keeps the same
> encoding/decoding metaphor while avoiding that collision, and still does
> not collide with existing tools like "Codebook LLMs", which is a paper
> name, not a product). Unlike the earlier Codifica→Cifra rename, this one
> did reach the repo name: the GitHub remote is now
> `mancano-tales/decifra-text-as-data` (renamed by the author 2026-09-03).
> The local package import path stays `text_as_data` — renaming that is
> still the cosmetic, deferred-to-later decision described below; only the
> product/repo name changed, not the Python package. The main working
> directory on this machine was deliberately **not** renamed to match: it
> is the hub for several active `git worktree` checkouts (see
> [`docs/MULTI_AGENT_WORKTREES.md`](docs/MULTI_AGENT_WORKTREES.md)), and
> renaming it would break their linked `.git` metadata. It keeps the
> `cifra-text-as-data` folder name until someone deliberately retires those
> worktrees and repairs the links — that folder name is now stale relative
> to the product/repo name, on purpose, until then.

### The problem

Social scientists (political science, sociology, geography) code
unstructured text (news articles, police reports, public statements) into
categorical variables that operationalize theoretical concepts — "is this a
protest?", "does this statement support or oppose policy X?". This has
historically been done by hand, with research assistants reading and
filling a spreadsheet. LLMs can now automate a lot of this, but every
researcher currently reinvents the pipeline from scratch, with no reusable
tool.

This is **not** a manual QDA tool (Taguette, QualCoder, QualiLab already
exist for that). It is the inverse: the researcher defines a codebook,
points at a corpus, and the software calls an LLM to fill the output table
automatically — with a validation step against human coding as a
first-class part of the pipeline, because LLMs do not follow codebooks with
perfect fidelity (see "Why validation is not optional" below).

**What "automated" does and does not mean**: automation applies only to the
mechanical coding step — text becomes a category without an RA reading
every row. It does not remove the researcher from the rest of the process.
The researcher is still solely responsible for: designing the codebook
(which categories exist, how each is defined, where the conceptual
boundaries are), deciding the pipeline's architecture (which corpus, which
model, which parameters), interpreting results, and deciding — via the
validation step — whether the automated coding is reliable enough to become
research data. The software automates mechanical execution, not the
theoretical decision of what is being measured. This should be explicit in
the UI too: the Codebook Editor (Screen 2) is the most important screen in
the software, not a secondary form before "the real part".

### MVP scope (v0.1) — build in this order

1. **Import corpus**: CSV/XLSX (one row = one document; user maps which
   column is the text), standalone TXT/DOCX/PDF, or pasted text. No
   automated web scraping in this version — this is local file ingestion.
2. **Codebook editor**: an interface to define a concept with categories.
   Each category has: name, definition, positive examples, negative
   examples, boundary notes ("do not confuse with Y"). See exact format
   below.
3. **Run extraction**: runs the LLM over each corpus document using the
   codebook as system instructions + structured output (JSON Schema).
   Needs: a queue with visible progress, automatic retry on
   network/rate-limit errors, caching (do not re-code a document already
   processed with the same codebook+model), estimated cost (tokens) before
   running.
4. **Results table**: view/edit output row by row, export CSV/XLSX/JSON.
5. **Validation**: import a human-labeled subset (gold standard), compare
   against the LLM output, compute accuracy, Cohen's kappa,
   precision/recall/F1 per category, and list disagreements for manual
   reading (error analysis).

**Explicitly out of MVP scope** (do not build yet, only keep the
architecture ready for it): automated scraping of sites/social media,
model fine-tuning, multi-user/auth, image/scanned-PDF extraction (OCR).

**Scope reversal (2026-09-01)**: a bilingual PT-BR/EN UI, originally listed
above as out of scope, was requested by the author and built the same day
via `react-i18next` (`frontend/src/i18n.ts`, `frontend/src/locales/`), with
a language toggle in the app header persisted to `localStorage`. This
covers static UI copy across both existing screens; backend error `detail`
strings stay English-only (they carry interpolated identifiers like corpus
names, not safe to translate word-for-word) — the frontend shows a
localized generic message keyed off the HTTP status instead, with the raw
detail kept alongside as untranslated technical context (see
`frontend/src/errorMessages.ts`). Any new screen must extend this i18n
setup rather than reintroduce hardcoded English strings.

### Architecture (closed decision — do not reopen without a strong reason)

Why not a single-file HTML tool like QualiLab: **correction (2026-09-01)** —
an earlier version of this paragraph claimed QualiLab was "100% manual
coding" with no batched API calls. That was wrong, and was written without
reading QualiLab's source; verified by cloning
[`luizpf42/QualiLab`](https://github.com/luizpf42/QualiLab) (v1.4.50) and
reading `README.en.md` and `docs/MANUAL.en.md` directly. QualiLab does call
LLMs: five "Auto-coding" assistants (Suggest Coding, Suggest Attributes,
Define Attribute, Organize Codes, plus a non-AI Repeat Coding), an "Analyze
with AI" chat, an "Explore with AI" agentic/RAG mode, and a **blind
evaluation** feature that runs one call per document and returns an
agreement scoreboard — conceptually close to a validation step.

The real difference is not manual-vs-automated, it is architectural, and
holds up under inspection of the source:
- **Scale ceiling**: QualiLab caps a single send at ~600,000 characters
  (~200 pages) total, and documents beyond that are dropped entirely — "a
  generous selection fits... but not the whole corpus at once"
  (`MANUAL.en.md`). This project needs to run hundreds/thousands of LLM
  calls over a full corpus with no such ceiling.
- **Execution model**: QualiLab's AI calls are synchronous within the open
  browser tab, with no persistent job queue and no resumable run if the tab
  closes — a direct consequence of its deliberate single-file,
  no-server-of-its-own design ("Extensibility through data, not plugins... has no plugin architecture, and does not intend to have one: it clashes
  head-on with the single-file design," per its own README). This project's
  Phase 1 acceptance criterion — execution that survives closing the tab,
  with retry and cache — requires a real backend process.
- **Validation rigor**: QualiLab's blind-evaluation scoreboard explicitly
  disclaims statistical rigor ("it does not tell 27 from 28... read it as
  an order of magnitude, not a grade" — `MANUAL.en.md`). It is an agreement
  count, not Cohen's kappa or per-category precision/recall/F1.

QualiLab's own stated extension surface is **not** code contribution but
its open `.qualilab` file format (documented, lossless JSON) — worth
revisiting as an import/export target for corpus interop, rather than as a
reason to build inside its codebase.

**Stack decision**: a lightweight local backend (Python), not a
single-file browser app. Batched LLM calls need retry/cache/cost control
and processing that survives closing the tab — uncomfortable and unsafe
(exposed API key) if done only in browser JS.

**Product trajectory** (a roadmap, not a day-1 requirement): the long-term
goal is a packaged desktop app (Windows/Mac/Linux), not a script only the
author knows how to run. This does **not** mean building in Tauri/Electron
from day one — it means building the Python backend so that packaging is a
packaging step later, not a rewrite:

- **Phase 1 (now)**: standalone FastAPI backend, "sidecar-ready" from the
  first commit — a single process that comes up on a local port, with no
  dependency on browser/session state, all persistence in local SQLite.
  **Acceptance criterion**: the backend must come up and respond via
  `curl` with no frontend open. If that stops being true at any point
  during development, it is a sign of improper front/back coupling — fix
  it before continuing.
- **Phase 2 (packaging, only after the pipeline is validated with real
  use)**: compile the Python backend into a single binary via PyInstaller
  (or Nuitka), and use Tauri (preferred over Electron — uses the system
  webview, much lighter) as the desktop shell, auto-starting that binary as
  a sidecar when the app opens. The LLM/validation/cache logic is not
  rewritten — only packaged. This is the same pattern used by today's
  popular desktop AI apps (e.g. local-LLM apps running a Node/Python
  process behind an Electron/Tauri window) — it is the standard
  industry architecture for "desktop GUI + local AI engine", not a hack.
- **Why not jump straight to Tauri with native (Rust/TS) logic**:
  rewriting LLM orchestration, retry/cache, and kappa computation in
  Rust/TypeScript costs real engineering and throws away the advantage of
  the Python ecosystem (mature LLM SDKs, `scipy`/`scikit-learn` for
  validation metrics, scraping libraries if scope grows). Only consider
  that route if the Python sidecar proves genuinely problematic for
  cross-platform distribution in practice.
- **Backend**: Python + FastAPI, running locally (`uvicorn`). Responsible
  for: LLM calls (see "LLM provider" below), a background job queue
  (nothing heavier than needed — no Redis/Celery in the MVP), and a SQLite
  database (`sqlmodel`) holding codebooks, corpus, runs, and results.
- **Frontend**: a simple SPA talking to the backend over REST/fetch.
  Either in QualiLab's "no heavy build" spirit (Preact + htm via CDN) or a
  light Vite+React app — implementer's call at build time, as long as it
  does not add build complexity a project this size does not need.
  Important for Phase 2: pick something Tauri can embed as a webview
  without friction (both options qualify).
- **Local execution (Phase 1)**: `pip install -e .` + a `codifica serve`
  (or similar) command brings up backend+frontend on a local port; the
  user opens it in a browser. Credentials are entered once in the UI and
  saved to local config (see "LLM provider" below for the two supported
  credential modes) — nothing is ever sent anywhere except the chosen
  provider's own API/CLI. In Phase 2 this migrates to the OS's native
  secure storage (e.g. a Tauri keychain plugin), but the "paste your
  credential once" UX stays the same.
- No cloud/third-party server in the MVP. If a collaborative mode ever
  makes sense later (like QualiLab's Supabase mode), treat it as v3, after
  desktop packaging.

**LLM provider — agent-agnostic (decided 2026-08-31)**: the provider layer
supports two credential modes side by side, both behind one thin interface
(`get_client(mode, provider)` or similar — exact shape is Slice 1
implementation work, not yet written):
1. **CLI mode**: shells out to an already-installed CLI the user has a
   subscription for — Claude Code CLI (`claude -p`), a Codex-style CLI
   (`codex exec`), or a generic configurable "command + prompt template"
   adapter for anything else compatible. No separate metered API key
   needed if the user already pays for a CLI subscription. **Best-effort
   only**: unlike the API-key path, a CLI has no schema-enforcement
   mechanism equivalent to `instructor`'s function-calling constraint —
   the prompt asks for JSON, the response is parsed, and malformed output
   is retried. Accept a higher error rate here; this is the tradeoff for
   not requiring a billed API key.
2. **API-key mode**: a direct key (OpenAI and/or Anthropic) via the
   `instructor` SDK pattern already used in the toy example — the
   recommended, guaranteed-schema path for real, large coding runs.
Both modes implement the same interface so `extraction.py` does not care
which one is active; `codebook.py`'s dynamically-derived Pydantic schema is
the contract both must honor.

### Codebook format

Based on Halterman & Keith's "Stage 0: Codebook Preparation" (2025,
*Political Analysis*, "Codebook LLMs") — a format readable by both humans
and LLMs. Stored as YAML (editable outside the GUI too) and as rows in
SQLite:

```yaml
concept: protest
description: >
  A collective, public event expressing a political or social claim,
  involving at least two people.
categories:
  - label: protest
    definition: >
      An occupation, march, or strike with a declared political demand, or
      a road blockade with a stated claim.
    positive_examples:
      - "About 200 people occupied the square in front of city hall..."
    negative_examples:
      - "People gathered for a cultural event with no political claim"
    boundary_notes: >
      Does not include purely ceremonial/commemorative events with no
      claim being made. A labor strike with no political demand is a
      boundary case — decide explicitly whether to include or exclude it.
  - label: not_protest
    definition: "Any event that does not meet the criteria above."
```

The LLM's structured output must be forced via a JSON Schema derived
directly from this codebook (an `enum` of the category `label`s, plus a
free-text `rationale` field and an `evidence_span` field quoting the part
of the document that grounded the decision — this is what makes the
decision auditable later).

### Data model (SQLite tables, high level)

- `codebooks` (id, name, yaml_raw, created_at)
- `documents` (id, corpus_id, text, metadata_json)
- `runs` (id, codebook_id, corpus_id, model, status, created_at)
- `extractions` (id, run_id, document_id, category, rationale,
  evidence_span, tokens_used)
- `human_labels` (id, document_id, codebook_id, category, coder)

### Screens (main flow)

1. **Corpus** — import/list documents
2. **Codebook** — create/edit codebook (a structured form, not raw YAML)
3. **Run** — pick corpus + codebook + model, watch progress, estimated cost
4. **Results** — browsable table, filter by category, export
5. **Validation** — import human gold labels, view agreement metrics and
   the list of disagreements

### Why the validation step is not optional

Read before simplifying this part: Halterman & Keith (2025) and the same
group's 2026 follow-up ("What is a protest anyway?", ACL 2026) show that
off-the-shelf LLMs frequently ignore a codebook's specific
operationalization and fall back on their own generic notion of the
concept (e.g. including a labor strike under "protest" even when the
codebook explicitly excludes it). That is why the Validation screen with
Cohen's kappa and manual disagreement review is not a "nice to have" — it
is this tool's actual scientific differentiator over just calling the API
directly from a script.

### Build order for the MVP (agreed 2026-08-31, via brainstorming)

The 5-screen MVP is too large for one implementation plan. Build order:

1. **Slice 1 — thin backend skeleton** (done, 2026-09-01): FastAPI + SQLite,
   engine adapted to load the YAML codebook format above and derive the
   Pydantic schema dynamically, real pilot data (see below, not the toy
   example), with minimal caching/retry and a `curl`-testable API. No
   frontend yet — that is Slice 2's job, matching the Phase 1 acceptance
   criterion above ("backend responds via curl with no frontend open").
   Final end-to-end verification (Task 10) ran the real backend against
   the real V7 pilot data using **CLI mode** (`claude -p`), not API-key
   mode — no `ANTHROPIC_API_KEY` was available in that environment, so
   this was a genuine exercise of the provider layer's own agent-agnostic
   design, not a shortcut. Outcome: both hypothesis sides (`H1_a`, `H1_b`)
   ran successfully end-to-end via `curl`, but the LLM's `categoria`
   (`cinquenta_e_cinquenta` for both) disagreed with the human gold label
   (`provavel` for both) — 0/2 agreement on this tiny 2-point sanity
   check, not a real validation result (see "Real-world pilot data" below
   for why the gold set is this small). Two genuine Windows-specific bugs
   were found in `CliProvider` (`src/text_as_data/providers.py`) during
   this run: (a) `subprocess.run(["claude", "-p"], ...)` failed with
   `FileNotFoundError: [WinError 2]` because `claude` resolves to an npm
   `.cmd` shim, which Windows cannot exec without `shell=True` or a fully
   resolved path; (b) `CliProvider.extract()`'s `subprocess.run(...,
   text=True)` call had no explicit `encoding=`, so on this Windows
   machine it silently decoded the CLI's UTF-8 stdout using the locale
   default (`cp1252`) instead, double-encoding any accented character in
   `trecho_evidencia`/`justificativa` (e.g. `instituições` became
   `institui\xc3\x83\xc2\xa7\xc3\x83\xc2\xb5es` at the byte level —
   confirmed, not a terminal display artifact); the `categoria` enum
   itself is ASCII-only and was unaffected. **Both fixed same-day**
   (commit `91c6b5e`): `__init__` now resolves `command[0]` via
   `shutil.which()` once per instance (falling back to the original name,
   so a genuinely-missing CLI still raises its own clear error), and
   `extract()` passes `encoding="utf-8"` explicitly instead of `text=True`.
   4 new regression tests cover both fixes.
2. **Slice 2+** — one spec/plan per screen (Corpus import, Codebook
   editor, Run + Results, Validation), each building on the skeleton.

### Real-world pilot data (located 2026-08-31, in `Reforming-TE-PT`)

Located across three sibling repositories (`Mancano2026-MA-Thesis`,
`Reforming-TE-PT`, `folha-scraper` — all read under the explicit
authorization of `0-meta/plan/2026-08-31_Plano_Desenvolver_App_Codifica_MVP.md`
WP4 in the root). Chosen pilot: **Option A, the `Reforming-TE-PT`
Bayesian process-tracing workbook** (not the Folha relevance-triage
few-shot pipeline in `Mancano2026-MA-Thesis/4-DA-Code/2026-05_Folha_Scraper`,
which was the simpler alternative).

- **Source**: `Reforming-TE-PT/v7_banco_process_tracing_baesiano_abdutivo_manual.xlsx`
  (documented externally in that repo's `readme_v7_banco_process_tracing.md`
  — read that file, not the `.xlsx` directly, to understand structure).
  Operationalizes Fairfield & Charman (2022) Bayesian process tracing: each
  row of evidence is evaluated against a pair of competing hypotheses on a
  7-level verbal probability scale (`quase_certa` … `quase_impossivel`).
- **How this maps onto the Decifra codebook format**: cleanly, no engine
  redesign needed. `categoria` enum = the 7 verbal-probability labels;
  `justificativa` = `ek_justificativa_likelihoods` (the human's own
  reasoning, already the field the workbook's manual calls "the most
  important"); `trecho_evidencia` ≈ the evidence text itself /
  `Detalhe_Decisivo`. The same codebook schema runs **twice per evidence
  row** — once framed "inhabiting" each side of the hypothesis pair (e.g.
  H1a, then H1b) — producing `prob_e_dado_h1` and `prob_e_dado_h2`.
- **Corpus**: `tb3_evidence_raw` sheet, column `complete_evidence_content`
  (443 rows total, Folha articles and other sources from the 1990s–2010s).
- **Gold labels for validation — small, use anyway (decided 2026-08-31,
  refined 2026-09-01 after real import)**: of 999 rows in
  `tb4_evidence_analisys`, **7 have both `prob_e_dado_h1` and
  `prob_e_dado_h2` filled, and only 5 have `ek_justificativa_likelihoods`**
  — the workbook is still "em coleta", not a finished instrument. Author
  explicitly chose to proceed with this small set for Slice 1: enough to
  prove the pipeline runs end-to-end against real data, not enough for a
  real Cohen's kappa. **However**, running Task 7's real import
  (`scripts/import_v7_pilot.py`) against those 7 rows found the usable
  count is smaller still: only **2 of the 7** resolve to a real
  hypothesis-pair definition via `tb1_hypotheses` (joined on the real
  column name `pk_hyp__code`, not `pk_hyp_pair_code` as originally
  documented here), and of those 2, only **1** (the `H1` pair) has a
  usable `fk_id_ev` join to `tb3_evidence_raw` — the other candidate
  (`H3`) has `fk_id_ev=None` and `#N/A` evidence content in the source
  workbook itself, so it is unrecoverable, not a pipeline bug. Net result:
  Slice 1's real pilot run ended up with **1 usable gold evidence row**,
  validated across both sides of its hypothesis pair (`H1_a`/`H1_b` =
  2 gold data points), not 2 evidence rows as originally estimated. This
  is real, useful signal for anyone deciding whether to hand-code more V7
  rows before Slice 2 — the effective gold set is smaller than "7 rows"
  suggests. A validation slice with statistical power waits until more
  rows are hand-coded *and* correctly linked to `tb1_hypotheses`.
  **Known naming inconsistency**: of the original 7 candidate rows, most
  (`4`) use the workbook's *old* hypothesis-group vocabulary
  (`H_nao_partidaria`, etc.) rather than the current `H1`/`H2`/`H3`
  numbering the manual documents as current since 2026-06-08 — handle both
  when joining `tb3`/`tb4`.
- **Known data-quality issue — mojibake, must fix before use (decided
  2026-08-31)**: `complete_evidence_content` and other text fields are
  corrupted (e.g. `institui��es` instead of `instituições`) — a
  Windows-1252/Latin-1-read-as-something-else bug from the original Folha
  scrape, not introduced by reading the file. Detect and re-normalize to
  correct UTF-8 as part of the corpus-import step for this slice, before
  any text reaches the LLM.
- **Live-file caution**: a LibreOffice/OnlyOffice lock file
  (`.~lock.v7_..._manual.xlsx#`) exists next to the workbook, dated
  2026-08-27 — 4 days old at time of writing, likely stale, but confirm
  the file is not actually open before writing to it (reading is always
  safe).
