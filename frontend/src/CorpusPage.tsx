import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { createCorpusFromDocuments, createCorpusFromCsv, createCorpusFromPaste, createCorpusFromXlsx, listCorpora } from "./api";
import type { CorpusSummary } from "./api";
import { describeApiError } from "./errorMessages";

export function CorpusPage() {
  const { t } = useTranslation();
  const [corpora, setCorpora] = useState<CorpusSummary[]>([]);
  const [error, setError] = useState<unknown>(null);
  const shownError = error ? describeApiError(error, t) : null;

  const [documentName, setDocumentName] = useState("");
  const [documentFiles, setDocumentFiles] = useState<File[]>([]);
  const [documentBusy, setDocumentBusy] = useState(false);
  const documentInput = useRef<HTMLInputElement>(null);
  const [notice, setNotice] = useState("");
  const [pasteName, setPasteName] = useState("");
  const [pasteText, setPasteText] = useState("");

  const [csvName, setCsvName] = useState("");
  const [csvColumn, setCsvColumn] = useState("");
  const [csvFile, setCsvFile] = useState<File | null>(null);

  const [xlsxName, setXlsxName] = useState("");
  const [xlsxColumn, setXlsxColumn] = useState("");
  const [xlsxFile, setXlsxFile] = useState<File | null>(null);

  // One flag per form -- a double-click (or a slow upload) on one form
  // must not block the other two, unrelated forms.
  const [pasteSubmitting, setPasteSubmitting] = useState(false);
  const [csvSubmitting, setCsvSubmitting] = useState(false);
  const [xlsxSubmitting, setXlsxSubmitting] = useState(false);

  // `setCsvFile(null)`/`setXlsxFile(null)` alone leaves the native file
  // input showing its last-picked filename -- browsers only let a file
  // input's `value` be programmatically set to `""`, never restored from
  // state, so the displayed filename and the (cleared) React state
  // silently drift apart after a successful upload unless the DOM
  // element itself is reset too.
  const csvFileInputRef = useRef<HTMLInputElement>(null);
  const xlsxFileInputRef = useRef<HTMLInputElement>(null);

  async function refresh() {
    try {
      setCorpora(await listCorpora());
    } catch (err) {
      setError(err);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handlePaste(event: FormEvent) {
    event.preventDefault();
    if (pasteSubmitting) return;
    setError(null);
    setPasteSubmitting(true);
    try {
      await createCorpusFromPaste(pasteName, pasteText);
      setPasteName("");
      setPasteText("");
      await refresh();
    } catch (err) {
      setError(err);
    } finally {
      setPasteSubmitting(false);
    }
  }

  async function handleCsv(event: FormEvent) {
    event.preventDefault();
    if (csvSubmitting) return;
    setError(null);
    if (!csvFile) return;
    setCsvSubmitting(true);
    try {
      await createCorpusFromCsv(csvName, csvColumn, csvFile);
      setCsvName("");
      setCsvColumn("");
      setCsvFile(null);
      if (csvFileInputRef.current) csvFileInputRef.current.value = "";
      await refresh();
    } catch (err) {
      setError(err);
    } finally {
      setCsvSubmitting(false);
    }
  }

  async function handleXlsx(event: FormEvent) {
    event.preventDefault();
    if (xlsxSubmitting) return;
    setError(null);
    if (!xlsxFile) return;
    setXlsxSubmitting(true);
    try {
      await createCorpusFromXlsx(xlsxName, xlsxColumn, xlsxFile);
      setXlsxName("");
      setXlsxColumn("");
      setXlsxFile(null);
      if (xlsxFileInputRef.current) xlsxFileInputRef.current.value = "";
      await refresh();
    } catch (err) {
      setError(err);
    } finally {
      setXlsxSubmitting(false);
    }
  }

  return (
    <div className="screen">
      {shownError && (
        <div className="banner-error">
          {shownError.message}
          {shownError.detail && <div className="banner-error-detail">{shownError.detail}</div>}
        </div>
      )}

      <section className="card">
        <h2 className="card-title">{t("corpus.existingTitle")}</h2>
        {corpora.length === 0 ? (
          <p className="empty-state">{t("corpus.empty")}</p>
        ) : (
          <ul className="corpus-list">
            {corpora.map((c) => (
              <li key={c.corpus_id}>
                <span className="corpus-id">{c.corpus_id}</span>
                <span className="pill">{t("corpus.docCount", { count: c.document_count })}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {notice && <p role="status">{notice}</p>}
      <div className="card-grid">
        <form className="card" onSubmit={async e => {
          e.preventDefault(); if(documentBusy) return; setDocumentBusy(true); setError(null); setNotice("");
          try {const result=await createCorpusFromDocuments(documentName,documentFiles); setNotice(t("corpus.imported",{count:result.document_count})); setDocumentName(""); setDocumentFiles([]); if(documentInput.current) documentInput.current.value=""; await refresh();} catch(e) {setError(e);} finally {setDocumentBusy(false);}
        }}>
          <h3 className="card-title">{t("corpus.documentsTitle")}</h3>
          <p>{t("corpus.documentsHelp")}</p>
          <div className="field"><label htmlFor="documents-name">{t("corpus.corpusName")}</label><input id="documents-name" required value={documentName} onChange={e=>setDocumentName(e.target.value)}/></div>
          <div className="field"><label htmlFor="documents-files">{t("corpus.file")}</label><input id="documents-files" ref={documentInput} type="file" multiple required accept=".txt,.md,.docx,.pdf" onChange={e=>setDocumentFiles(Array.from(e.target.files ?? []))}/></div>
          <button className="btn btn-primary" disabled={documentBusy || !documentFiles.length}>{t("corpus.upload")}</button>
        </form>
        <form className="card" onSubmit={handlePaste}>
          <h3 className="card-title">{t("corpus.pasteTitle")}</h3>
          <div className="field">
            <label className="field-label" htmlFor="paste-name">
              {t("corpus.corpusName")}
            </label>
            <input
              id="paste-name"
              value={pasteName}
              onChange={(e) => setPasteName(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="paste-text">
              {t("corpus.text")}
            </label>
            <textarea id="paste-text" value={pasteText} onChange={(e) => setPasteText(e.target.value)} required />
          </div>
          <button className="btn btn-primary" type="submit" disabled={pasteSubmitting}>
            {t("corpus.add")}
          </button>
        </form>

        <form className="card" onSubmit={handleCsv}>
          <h3 className="card-title">{t("corpus.csvTitle")}</h3>
          <div className="field">
            <label className="field-label" htmlFor="csv-name">
              {t("corpus.corpusName")}
            </label>
            <input id="csv-name" value={csvName} onChange={(e) => setCsvName(e.target.value)} required />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="csv-column">
              {t("corpus.textColumn")}
            </label>
            <input id="csv-column" value={csvColumn} onChange={(e) => setCsvColumn(e.target.value)} required />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="csv-file">
              {t("corpus.file")}
            </label>
            <input
              id="csv-file"
              ref={csvFileInputRef}
              type="file"
              accept=".csv"
              onChange={(e) => setCsvFile(e.target.files?.[0] ?? null)}
              required
            />
          </div>
          <button className="btn btn-primary" type="submit" disabled={csvSubmitting}>
            {t("corpus.upload")}
          </button>
        </form>

        <form className="card" onSubmit={handleXlsx}>
          <h3 className="card-title">{t("corpus.xlsxTitle")}</h3>
          <div className="field">
            <label className="field-label" htmlFor="xlsx-name">
              {t("corpus.corpusName")}
            </label>
            <input id="xlsx-name" value={xlsxName} onChange={(e) => setXlsxName(e.target.value)} required />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="xlsx-column">
              {t("corpus.textColumn")}
            </label>
            <input id="xlsx-column" value={xlsxColumn} onChange={(e) => setXlsxColumn(e.target.value)} required />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="xlsx-file">
              {t("corpus.file")}
            </label>
            <input
              id="xlsx-file"
              ref={xlsxFileInputRef}
              type="file"
              accept=".xlsx"
              onChange={(e) => setXlsxFile(e.target.files?.[0] ?? null)}
              required
            />
          </div>
          <button className="btn btn-primary" type="submit" disabled={xlsxSubmitting}>
            {t("corpus.upload")}
          </button>
        </form>
      </div>
    </div>
  );
}
