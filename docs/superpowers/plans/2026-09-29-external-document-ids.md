# External document ids through import, results and gold labels — Implementation Plan

> **Status:** Approved by the author in chat on 2026-09-29, as work package WP-B of the bbsia-radar MVP plan ([bbsia-radar#28](https://github.com/mancano-tales/bbsia-radar/issues/28)). Implemented on branch `claude/4-external-id`; the PR needs a `@codex review` and the author's merge.
> **Issue:** [#4](https://github.com/mancano-tales/decifra-text-as-data/issues/4) (requirement 3 and the 2026-09-28 request).
> **Spec:** this plan carries its own short design (§ Design). The change is additive, touches no codebook or extraction logic, and reuses the `DocumentRecord.external_id` column that the QualiLab interop already added.

**Goal:** A caller that imports a spreadsheet corpus can name one column as its own stable document id, see that id next to every result and export row, and upload gold labels keyed by it. The radar can then match Decifra's results to its 104 candidates without relying on row order.

**Problem:** `POST /corpora/csv` and `/corpora/xlsx` kept only the text column. Every other column, the caller's id included, was dropped before documents were written, so results could be joined back only by position.

## Design

1. **Import.** Both spreadsheet endpoints accept an optional form field `id_column`. Without it, behavior is unchanged and `external_id` stays `NULL`. With it:
   - the column must exist (422 listing the available columns, as for `text_column`);
   - ids are trimmed; XLSX integral floats (`102.0`) are written as integers (`102`) so a numeric id keeps the caller's spelling;
   - every row that is kept (non-blank text) must have a non-blank id, unique within the file; otherwise the whole upload is rejected with 422, naming the blank lines and repeated values, and nothing is written. Rows skipped for blank text are ignored, ids included.
2. **Results and export.** `GET /runs/{id}/results`, `PUT /runs/{id}/results/{extraction_id}` and every `GET /runs/{id}/export` format gain `document_external_id` (`null` when the corpus has none), placed before `document_snippet`.
3. **Gold labels.** `POST /runs/{id}/gold-labels` accepts either `document_id` or `document_external_id` as the row key. `document_id` wins when both are filled, so every existing gold file behaves exactly as before. An external id is resolved only inside the run's corpus; an unknown one rejects the upload and is named in the error.

Out of scope: a uniqueness constraint in SQLite (the check lives at import, where a corpus is created in one request), exposing `id_column` in the frontend import screen, and multi-variable gold labels (the endpoint still reads the single-variable `categories` list, unchanged here).

## Tasks

- [x] **1. Tests first.** `tests/test_app_external_id.py`: CSV and XLSX import with and without `id_column`, unknown column, blank and repeated ids, rows skipped for blank text, trimming, XLSX numeric ids, results and all three export formats, gold labels by external id, precedence of `document_id`, unknown external id, and the missing-id-column error. Twelve of fourteen failed before the change; the two that passed describe the unchanged default behavior.
- [x] **2. Import.** `_rows_to_texts` became `_rows_to_documents`, returning `(text, external_id)` pairs; `_create_documents_or_409` writes `external_id`.
- [x] **3. Results and export.** `_extraction_with_snippet` and `_extractions_with_snippets` add `document_external_id` from the documents they already load, so no extra query per row.
- [x] **4. Gold labels.** Resolve `document_external_id` within the run's corpus; keep `document_id` authoritative.
- [x] **5. Record and verify.** Full pytest: 361 passed (347 before, 14 new). The `ExtractionResult` type in `frontend/src/api.ts` gained the optional field. No `NEWS.md` entry: the author retired `NEWS.md` across the ecosystem on 2026-09-28 (hub issue #37); this repository's governance block predates that decision and has not been synced yet. The PR uses `Refs #4`, because #4 also asks for the radar pilot run, which happens in bbsia-radar.

## Acceptance evidence

`PYTHONPATH=src pytest`: 361 passed. The radar round trip is exercised by `tests/test_app_external_id.py` with radar-shaped ids (`github:101`, `huggingface:neuralmind/bert`).

## Risks and boundaries

- The results payload gains one key. Frontend consumers that ignore unknown keys are unaffected; the build is checked before the PR.
- The radar still does not import Decifra code: it uploads a CSV with `id_column=id` and reads `document_external_id` from the export.
