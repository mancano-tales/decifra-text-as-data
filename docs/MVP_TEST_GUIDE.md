# Test the MVP locally

Verification on 2026-09-07: 267 distinct tests passed; frontend lint/build passed; a browser-started three-document live CLI run completed with all source quotations verified.

This is a supervised single-variable pilot. The corpus and codebook supplied for the handoff are synthetic and are not research data.

## Start

After installing the editable Python package and frontend dependencies:

```powershell
cd frontend
npm ci
npm run build
cd ..
.venv/Scripts/python.exe scripts/build_frontend.py
powershell -File scripts/start_pilot.ps1
```

Open http://127.0.0.1:8765. The script keeps this checkout's pilot data under `data/pilot` and settings under `data/pilot/config`. Closing the browser does not stop a run; stopping the backend does. Keep the server terminal running. For the general app entry point, `decifra serve` uses the OS user data directory; it does not migrate old repository databases automatically.

## Suggested test (10 minutes)

1. Open Settings. Confirm CLI mode and the installed, authenticated command. Defaults affect new runs. API keys can instead be saved to the OS credential vault; the UI never reads them back.
2. Import your own small corpus: pasted text, CSV/XLSX with a text column, or TXT/Markdown/DOCX/text PDF files. Each standalone file is one document. Scanned PDFs need OCR elsewhere.
3. Create a codebook with two clear categories and examples, or use the synthetic sample provided during handoff.
4. In Runs, choose corpus/codebook/model, click Estimate usage, inspect cache/token counts, then Start. CLI model is an audit label: configure the actual model in the CLI command/tool itself. Estimates are approximations, not spending caps; optional monetary estimates use your entered rates.
5. Check each category, rationale, quotation and its source-match badge. Expand the prompt/response panel. Edit one result and verify its original is retained there.
6. Export CSV, add a `gold_categoria` column with your independent human coding, then upload it in Validation. Keep the `document_id` values from the export. Check disagreements and metrics. Use an independent gold set to assess quality, not agreement after manually correcting all predictions.
7. Repeat the same run to exercise cache. Select Ignore cache for an actual new model call.

## Known boundaries

Single-variable schema; no installer or OCR. No durable cancellation/resume after backend shutdown. Version-aware gold-label storage and a complete scientific disclosure report are future work. Review preserves the first original answer but does not yet keep every intermediate edit as a separate event. API usage is recorded when exposed by the SDK; failed/retried calls may not all be included. A successful synthetic run validates operation, not scientific accuracy.
