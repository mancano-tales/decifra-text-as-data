# Decifra: verified MVP status

## Update: functional MVP handoff (2026-09-07)

The follow-up implementation closes document import in the UI and adds approximate pre-run token/cache estimates, optional user-entered monetary rates, persisted provider defaults, OS-keyring credential entry, and `decifra serve` with one local frontend/API origin. It also surfaces evidence and errors, preserves the original pre-review answer, excludes reviewed rows from cache, scopes validation coverage to the corpus, and records SDK-reported tokens when available.

Verification: 267 distinct tests passed (266-test full suite plus the final eight-test handoff regression run, including one added coverage test), and frontend lint/build passed (three existing frontend warnings). The browser-started real CLI run classified three synthetic Portuguese documents, all with verified quotations. Browser document upload, settings save, result review/original preservation, CSV export and synthetic gold-label validation also passed. Local handoff URL: http://127.0.0.1:8765. See [the test guide](MVP_TEST_GUIDE.md) for startup and remaining limitations.

This is a functional single-variable MVP for supervised user testing, not a packaged or scientifically validated production release. Price rates are user supplied; estimates are approximate and exclude retries. Durable recovery, version-scoped gold labels and complete disclosure history remain open.

## Earlier audit (historical)

The following records the state before the handoff implementation; items closed above are no longer pending.

Assessment date: 2026-09-07. This assessment describes the local consolidated code, not a released package.

## Verdict and purpose

Decifra is a functional alpha with an end-to-end coding pipeline. It turns a corpus into structured categories, explanations, and source quotations using a researcher-defined codebook. Its purpose is to make model-assisted qualitative coding repeatable, inspectable, and comparable with human labels. It does not establish scientific validity automatically.

The five workflow stages exist within three navigation tabs: corpus, codebook, execution, results/review, and validation. This is sufficient for a supervised technical pilot; the original MVP acceptance is not fully satisfied. A percentage would obscure the missing user-facing requirements.

## Verification performed

- Python 3.12, a fresh worktree-local editable installation, and isolated SQLite test data.
- Full pytest suite: **259 passed, zero failures/errors/skips**, approximately 60 seconds. Command: `.venv/Scripts/python.exe -m pytest --basetemp=.verification/pytest-tmp-20260907a --junitxml=.verification/pytest.xml`.
- Frontend lint and production build passed. Lint retains three pre-existing React effect warnings (CorpusPage, RunsPage, CodebookEditor).
- Browser: pasted a synthetic document, created and saved its codebook, and submitted a CLI run. The successful live run is visible in the results interface.
- HTTP smoke with a deterministic CLI subprocess: CSV/XLSX/TXT/Markdown/DOCX imports, background execution, parsing, SQLite persistence, evidence verification, cache reuse without a new provider call, forced fresh execution, reproducibility, gold-label replacement, disagreements, and readable CSV/XLSX/JSON exports.
- The controlled two-document test produced accuracy/kappa 1.0 for matching labels and accuracy 0.5/kappa 0.0 after deliberately changing one label. These are plumbing checks, not estimates of model quality.
- **Real model check:** the installed Antigravity CLI successfully classified one synthetic protest document and returned a verified quotation. The first restricted execution could not access user authentication/log directories; a normal-user run succeeded. This confirms one authenticated CLI path, not every provider or large-corpus reliability. Direct Anthropic/OpenAI API calls were not exercised with live keys.
- Verification artifacts and the isolated test database remain in the integration worktree (`.verification/`, ignored). Original research databases were not used or modified. The historical V7 experiments were preserved, not rerun.

## Remaining work, ordered for a usable pilot

1. Finish original MVP gaps: show a pre-run cost estimate and expose document-file import in the interface (the backend import exists).
2. Make setup accessible: credentials/settings, one application entry point, frontend served by the backend, and a database in the user data directory. An installer remains future work.
3. Improve run recovery: cancellation/resume and distinguish completed runs with per-document errors from successful runs. Restart recovery needs attention.
4. Harden scientific audit: preserve original predictions separately from human edits; scope gold labels to the appropriate codebook version/corpus; ensure disclosure reflects the actual run and validation. The API stores parsed responses, not complete raw HTTP/provider traces.
5. Expose existing evidence/reproducibility functionality consistently in the UI, then conduct a supervised pilot with an adequate human-coded validation set.

Multi-variable codebooks and DeepSeek/OpenRouter are design documents, not implemented features. They are roadmap extensions; their presence in Git does not close the tasks. The multi-variable YAML design still needs the author's sign-off before implementation. Krippendorff alpha, Gwet AC1, packaging, and additional provider paths also remain future work.

## Consolidation inventory

| Source branch | Unique work | Disposition |
| --- | --- | --- |
| `worktree-v7-pipeline-tuning` | V7 API experiment scripts/report | Merged with history (`bf32d72`) |
| `agent/r1.1-multi-variable-codebooks` | Three design revisions | Merged with history (`73cf3de`); implementation remains pending |
| `worktree-multi-provider-llm-2` | Untracked provider design | Preserved in `docs/superpowers/specs/`; tracked commits already in main |
| `feat/r2.4-cifra-entry-point` | No unique implementation | Already contained in main; R2.4 remains pending |
| `worktree-multi-provider-llm` | Missing, locked checkout; no unique commits | Historical branch already contained in main |
| Original main checkout | Two untracked research reports | Preserved in `docs/research/` |

Consolidation centralizes source history and documents. Existing worktree folders, ignored databases, environments, and unrelated untracked files are preserved. It does not imply deletion of working directories or publication to GitHub. Historical research/provider claims were not independently revalidated in this audit.

## Fixes made during verification

Database initialization is now lazy and protected by a lock: importing the web app no longer creates a SQLite file or races a simultaneously starting server. Regression tests cover import side effects and concurrent initialization. Development launchers use their own virtual environment and pass the selected API port to Vite; the Windows launcher starts hidden processes and cleans up its children. The preserved V7 scripts create output directories and use a consistent model identifier. Both READMEs and the site now distinguish implemented functionality from planned work.

Learning: a developer environment or an import-time side effect can masquerade as a product failure. Separate filesystem/authentication failures from model output failures, and distinguish controlled integration tests from live-provider checks.
