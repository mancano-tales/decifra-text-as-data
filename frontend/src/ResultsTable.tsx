import { useState } from "react";
import { useTranslation } from "react-i18next";
import { exportRunUrl, updateExtraction } from "./api";
import type { ExtractionResult } from "./api";
import { ValidationPanel } from "./ValidationPanel";

interface ResultsTableProps {
  runId: number;
  results: ExtractionResult[];
  codebookLabels: string[];
  // Takes an updater function (not a computed array) so saveEdit doesn't
  // have to close over `results` -- two rows saved in close succession
  // (Row 2's save starting before Row 1's PUT resolves) would otherwise
  // both compute their update from the same stale `results` snapshot, and
  // whichever save's setState landed second would silently revert the
  // other's edit. React's setState already accepts this form directly.
  onResultsChange: (updater: (prev: ExtractionResult[]) => ExtractionResult[]) => void;
  onError: (err: unknown) => void;
}

export function ResultsTable({ runId, results, codebookLabels, onResultsChange, onError }: ResultsTableProps) {
  const { t } = useTranslation();
  const [categoryFilter, setCategoryFilter] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editCategoria, setEditCategoria] = useState("");
  const [editJustificativa, setEditJustificativa] = useState("");
  const [savingId, setSavingId] = useState<number | null>(null);

  function startEdit(row: ExtractionResult) {
    setEditingId(row.id);
    setEditCategoria(row.categoria);
    setEditJustificativa(row.justificativa);
  }

  function cancelEdit() {
    setEditingId(null);
  }

  async function saveEdit(row: ExtractionResult) {
    if (savingId === row.id) return;
    setSavingId(row.id);
    try {
      const updated = await updateExtraction(runId, row.id, editCategoria, editJustificativa);
      onResultsChange((prev) => prev.map((r) => (r.id === row.id ? updated : r)));
      // Only clear the edit UI if the user is still editing this same row --
      // if they've since clicked "Edit" on a different row while this save
      // was in flight, clearing unconditionally would wipe that row's
      // in-progress (unsaved) edit instead.
      setEditingId((current) => (current === row.id ? null : current));
    } catch (err) {
      onError(err);
    } finally {
      setSavingId((current) => (current === row.id ? null : current));
    }
  }

  const filteredResults = categoryFilter ? results.filter((r) => r.categoria === categoryFilter) : results;
  // The filter must also list categories that actually occur in the
  // results but aren't in the current codebook -- the "__error__"
  // sentinel from a failed extraction, or a label since removed from the
  // codebook -- otherwise there's no way to filter down to exactly the
  // rows that need review.
  const filterOptions = Array.from(new Set([...codebookLabels, ...results.map((r) => r.categoria)]));

  return (
    <div>
      <h3 className="card-title">{t("runs.resultsTitle")}</h3>
      {results.some(r=>r.categoria === "__error__") && <div className="banner-error">{t("runs.documentErrors",{count:results.filter(r=>r.categoria === "__error__").length})}</div>}
      <div className="field">
        <label className="field-label" htmlFor="results-category-filter">
          {t("runs.filterByCategory")}
        </label>
        <select id="results-category-filter" value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
          <option value="">{t("runs.allCategories")}</option>
          {filterOptions.map((label) => (
            <option key={label} value={label}>
              {label}
            </option>
          ))}
        </select>
      </div>
      <div className="actions-row">
        <a className="btn" href={exportRunUrl(runId, "csv")} target="_blank" rel="noopener noreferrer">
          {t("runs.exportCsv")}
        </a>
        <a className="btn" href={exportRunUrl(runId, "xlsx")} target="_blank" rel="noopener noreferrer">
          {t("runs.exportXlsx")}
        </a>
        <a className="btn" href={exportRunUrl(runId, "json")} target="_blank" rel="noopener noreferrer">
          {t("runs.exportJson")}
        </a>
      </div>
      {filteredResults.length === 0 ? (
        <p className="empty-state">{t("runs.noResults")}</p>
      ) : (
        <table className="results-table">
          <thead>
            <tr>
              <th>{t("runs.colDocument")}</th>
              <th>{t("runs.colCategory")}</th>
              <th>{t("runs.colJustification")}</th>
              <th>{t("runs.evidence")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {filteredResults.map((row) => (
              <tr key={row.id}>
                <td>{row.document_snippet}</td>
                <td>
                  {editingId === row.id ? (
                    <select value={editCategoria} onChange={(e) => setEditCategoria(e.target.value)}>
                      {/* row.categoria can be a value not in codebookLabels -- the
                          "__error__" sentinel, or a label since removed from the
                          codebook. A <select> whose value matches no <option>
                          silently falls back to displaying the first option as
                          selected while the underlying state stays unchanged, so
                          clicking Save without noticing would submit the
                          original (invalid) value with no visible warning.
                          Surfacing it as its own option keeps what's displayed
                          in sync with what would actually be saved. */}
                      {!codebookLabels.includes(editCategoria) && (
                        <option value={editCategoria}>
                          {t("runs.unknownCategory", { value: editCategoria })}
                        </option>
                      )}
                      {codebookLabels.map((label) => (
                        <option key={label} value={label}>
                          {label}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className="pill">{row.categoria}</span>
                  )}
                </td>
                <td>
                  {editingId === row.id ? (
                    <textarea value={editJustificativa} onChange={(e) => setEditJustificativa(e.target.value)} />
                  ) : (
                    row.justificativa
                  )}
                </td>
                <td>
                  <blockquote>{row.trecho_evidencia || "—"}</blockquote>
                  <span className="pill">{t(row.evidence_verified ? "runs.evidenceVerified" : "runs.evidenceUnverified")}</span>
                  <details><summary>{t("runs.audit")}</summary><h4>{t("runs.prompt")}</h4><pre>{row.prompt_sent}</pre><h4>{t("runs.response")}</h4><pre>{row.raw_response}</pre>{row.original_result_json && <><h4>{t("runs.original")}</h4><pre>{row.original_result_json}</pre></>}</details>
                </td>
                <td>
                  {editingId === row.id ? (
                    <>
                      <button type="button" className="btn" onClick={() => saveEdit(row)} disabled={savingId === row.id}>
                        {t("runs.save")}
                      </button>
                      <button type="button" className="btn-ghost" onClick={cancelEdit}>
                        {t("runs.cancel")}
                      </button>
                    </>
                  ) : (
                    <button type="button" className="btn-danger-text" onClick={() => startEdit(row)}>
                      {t("runs.edit")}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <ValidationPanel runId={runId} onError={onError} />
    </div>
  );
}
