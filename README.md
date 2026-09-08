<!-- 🇺🇸 English — [🇧🇷 versão em português](README.pt-BR.md) -->

# decifra-text-as-data — Decifra

**Decifra** is a local-first tool for turning unstructured text (news articles, policy statements, police reports) into categorical data using an LLM against an explicit **codebook** you define — with a validation step against human-coded gold labels, because LLMs do not follow a codebook's specific operationalization with perfect fidelity.

It is not a manual qualitative-coding tool (see [Taguette](https://www.taguette.org/), [QualCoder](https://github.com/ccbogel/QualCoder), or [QualiLab](https://github.com/LuizPF42/QualiLab) for that). You define a codebook, point it at a corpus, and Decifra runs the LLM over every document and fills an output table automatically.

**Status:** functional single-variable MVP for a supervised pilot. The UI has four tabs (Corpus, Codebook, Runs, Settings); results and validation live inside Runs. Document upload, approximate pre-run token estimates, saved provider settings, evidence inspection and a single local server are implemented. No packaged installer yet. See the [test guide](docs/MVP_TEST_GUIDE.md).

For researchers, organizational analysts, data journalists, and NGOs who need categorical data from text with explicit coding rules and inspectable results. The application and database run locally; text is sent to the selected provider when using a remote model.

See [MVP status and consolidation evidence](docs/MVP_STATUS.md) for verified capabilities, remaining tasks, and testing limits.

---

## Why Decifra?

LLM text classification risks **construct validity**: does the model actually apply *your* specific operationalization of a concept, or does it fall back on a generic pre-trained notion (e.g. counting a labor strike as a "protest" even when your codebook excludes it)? See Halterman & Keith, *"Codebook LLMs: Evaluating LLMs as Measurement Tools for Political Science Concepts"* (*Political Analysis*, 2025). Decifra treats validating LLM output against human coding as a first-class step in the pipeline, not an afterthought.

---

## What's actually built

- **Codebook engine** (`text_as_data.codebook`): load a concept and its categories (definitions, positive/negative examples, boundary notes) from YAML, and derive a Pydantic schema and system prompt from it at runtime.
- **Two LLM provider modes** (`text_as_data.providers`):
  - **API-key mode**: `instructor`-enforced structured output over the Anthropic or OpenAI SDKs — the reliable path.
  - **CLI mode**: shells out to an already-installed, already-authenticated CLI (`claude -p`, `agy -p`, or a similar tool) instead of a metered API key. Best-effort — the schema is requested in the prompt and the JSON response is parsed, with retry on malformed output.
- **FastAPI backend + SQLite** (`text_as_data.app`, `text_as_data.db`): caches an extraction per (document, codebook hash, model) so re-running a batch doesn't re-pay for documents already coded; retries a failing document up to 3 times and records the error instead of crashing the run. Each extraction stores the prompt and response: full stdout in CLI mode, serialized parsed JSON in API-key mode (not the complete raw API envelope).
- **Validation** (`text_as_data.validation`): `agreement_report()` computes overall accuracy and Cohen's kappa, plus per-category precision, recall, and F1 against a human-coded gold set, and returns the list of disagreements for manual inspection.
- **Frontend** (`frontend/`, Vite + React + TypeScript): five workflow stages plus Settings — Corpus (paste text, or upload CSV/XLSX/TXT/Markdown/DOCX/text PDF), Codebook (structured form + YAML preview), Runs (start a run, watch progress), Results (browse/filter/edit the output table, export CSV/XLSX/JSON), and Validation (upload gold labels, view agreement metrics and disagreements). Bilingual PT-BR/EN.
- **Additional backend imports**: QualiLab corpus/gold-label import and result export remain API-only. Document upload now has a UI form (no OCR).
- **Settings and estimates**: OS-keyring API credentials, persisted run defaults, approximate prompt/schema token counts, cache counts, optional user-entered USD rates, and SDK-reported token usage when available. Estimates exclude possible retry costs.
- **Evidence and reproducibility**: source-quote verification is persisted in results/exports. `GET /runs/{id}/reproducibility?compare_to={id}` compares repeated runs; create the repeat with `bypass_cache: true`. The UI displays quotations and verification, exposes prompt/response details, and offers an ignore-cache checkbox. The run-comparison report remains API-only.
- **Disclosure** (`text_as_data.disclosure`): a backend methods-report scaffold. Some text is stale, and it reads the current codebook/checkout; it is not a complete historical validation or reproducibility report.

**Not built yet:** Multi-variable codebooks (design only). Cancel/resume and startup recovery of interrupted runs. Delete controls. Packaged installer. Parallel document processing (currently one document at a time). Krippendorff's alpha or Gwet's AC1 (only Cohen's kappa today). Direct API integrations beyond Anthropic and OpenAI (Gemini has been exercised through an external CLI; no native Gemini or local/Ollama integration).

---

## Installation (development)

```bash
python -m venv .venv
# Activate .venv/bin/activate on Unix or .venv/Scripts/Activate.ps1 in PowerShell.
python -m pip install -e ".[dev]"
cd frontend && npm ci && cd ..
```

You'll also need either an API key saved through Settings or an `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` environment variable (for API-key mode), or an already-installed, already-authenticated CLI like `claude` or `agy` (for CLI mode).

> **Note (multi-worktree environments):** An editable install points to a checkout within the Python environment used for installation. Sharing that environment across worktrees silently changes the import target. Use one `.venv` per worktree. If you have multiple worktrees, run the suite as `PYTHONPATH=src pytest` to bypass the editable install and hit the right source. See [`docs/MULTI_AGENT_WORKTREES.md`](docs/MULTI_AGENT_WORKTREES.md) for details.

---

## Running the MVP

After installation, build the UI once and launch one server:

```bash
npm --prefix frontend run build
python scripts/build_frontend.py
decifra serve
```

The browser opens at `http://127.0.0.1:8765`. The database lives in the OS user data directory. `--data-dir PATH` selects another directory; no old database is moved automatically. On Windows, `powershell -File scripts/start_pilot.ps1` instead keeps isolated pilot data/settings under this checkout's `data/pilot`. [Suggested test steps](docs/MVP_TEST_GUIDE.md).

## Running it (development)

For frontend development with live reloading, start the FastAPI backend and Vite together. `scripts/dev.sh` (macOS/Linux/Git Bash) and `scripts/dev.ps1` (native PowerShell) do that with one command instead of two terminals:

```bash
scripts/dev.sh              # backend on :8000, frontend on :5173
scripts/dev.sh 8010 5183    # optional: override both ports
```

```powershell
powershell -File scripts/dev.ps1
powershell -File scripts/dev.ps1 -BackendPort 8010 -FrontendPort 5183
```

Then open `http://localhost:5173`. Ctrl+C stops both processes.

---

## Quickstart (Python API)

### 1. Define a YAML codebook

```yaml
concept: protest
description: A collective public event expressing a political or social claim.
categories:
  - label: protest
    definition: An occupation, march, or rally with a declared political demand.
    positive_examples:
      - "About 200 students marched to city hall square demanding lower fares."
    negative_examples:
      - "People gathered for a music festival."
    boundary_notes: Does not include purely ceremonial parades.
  - label: not_protest
    definition: Any event that does not meet the criteria above.
```

### 2. Load it and run an extraction

```python
import instructor
import pandas as pd
from anthropic import Anthropic

from text_as_data import Codebook, extract

codebook = Codebook.from_yaml_file("codebook.yaml")
client = instructor.from_anthropic(Anthropic())
texts = pd.DataFrame({"id": [1], "text": ["About 200 people occupied the square..."]})

predicted = extract(texts, codebook, client, model="claude-sonnet-5")
```

`extract()` is a lightweight standalone Python helper; the backend uses `run_extraction()` for the persistent workflow. Use the backend if you want caching, retry, and CLI-mode support.

### 3. Or drive it through the backend

```bash
scripts/dev.sh   # in one terminal

curl -X POST http://localhost:8000/codebooks -H "Content-Type: application/json" -d '{
  "concept": "protest",
  "description": "A collective public event expressing a political or social claim.",
  "categories": [
    {"label": "protest", "definition": "An occupation, march, or rally with a declared political demand."},
    {"label": "not_protest", "definition": "Any event that does not meet the criteria above."}
  ]
}'
curl -X POST http://localhost:8000/corpora/paste -H "Content-Type: application/json" \
  -d '{"name": "demo", "text": "About 200 people occupied the square..."}'
curl -X POST http://localhost:8000/runs -H "Content-Type: application/json" \
  -d '{"codebook_id": 1, "corpus_id": "demo", "model": "claude-sonnet-5"}'
curl http://localhost:8000/runs/1/results
```

---

## Testing

```bash
PYTHONPATH=src pytest
```

Runs the backend test suite across the codebook engine, both provider modes, the SQLite models, the FastAPI endpoints, corpus import parsing, QualiLab interop, validation metrics, and the disclosure module.

---

## Packaging (not started)

The plan (see `AGENTS.md` § "Product trajectory") is a packaged desktop app — the Python backend compiled to a single binary, run locally, so installing Decifra is "download and open" rather than "clone a repo and run two dev servers." That work has not started. `AGENTS.md` gates it behind the pipeline being validated with real use first.
