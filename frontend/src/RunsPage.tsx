import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { getCodebook, getRun, getRunResults, listCodebooks, listCorpora, listRuns } from "./api";
import type { CodebookSummary, CorpusSummary, ExtractionResult, RunStatus, RunSummary } from "./api";
import { describeApiError } from "./errorMessages";
import { RunForm } from "./RunForm";
import { ResultsTable } from "./ResultsTable";

const ACTIVE_STATUSES = new Set(["pending", "running"]);

export function RunsPage() {
  const { t } = useTranslation();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [corpora, setCorpora] = useState<CorpusSummary[]>([]);
  const [codebooks, setCodebooks] = useState<CodebookSummary[]>([]);

  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [selectedStatus, setSelectedStatus] = useState<RunStatus | null>(null);
  const [results, setResults] = useState<ExtractionResult[] | null>(null);
  const [codebookLabels, setCodebookLabels] = useState<string[]>([]);
  const [error, setError] = useState<unknown>(null);
  const shownError = error ? describeApiError(error, t) : null;

  const pollRef = useRef<number | null>(null);
  // Guards against two classes of stale-async-response bugs: (a) a
  // request started before the component unmounted resolving after (and
  // trying to setState / start a new interval on a dead component); (b)
  // the user selecting a different run while a request for the
  // previously-selected one is still in flight, whose response would
  // otherwise land on top of the newly-selected run's UI. Every
  // selection bumps the token; a resolved request only applies its
  // result if the token it was issued under still matches.
  const isMountedRef = useRef(true);
  const selectionTokenRef = useRef(0);

  async function refreshRuns() {
    try {
      setRuns(await listRuns());
    } catch (err) {
      setError(err);
    }
  }

  async function loadFormOptions() {
    try {
      const [corporaList, codebooksList] = await Promise.all([listCorpora(), listCodebooks()]);
      setCorpora(corporaList);
      setCodebooks(codebooksList);
    } catch (err) {
      setError(err);
    }
  }

  useEffect(() => {
    isMountedRef.current = true;
    refreshRuns();
    loadFormOptions();
    return () => {
      isMountedRef.current = false;
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, []);

  function stopPolling() {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  function isStale(token: number): boolean {
    return !isMountedRef.current || token !== selectionTokenRef.current;
  }

  async function loadRunDetail(runId: number, codebookId: number, token: number) {
    try {
      const status = await getRun(runId);
      if (isStale(token)) return;
      setSelectedStatus(status);

      if (ACTIVE_STATUSES.has(status.status)) {
        if (!pollRef.current) {
          pollRef.current = window.setInterval(() => loadRunDetail(runId, codebookId, token), 2000);
        }
        return;
      }

      stopPolling();
      await refreshRuns();
      if (isStale(token)) return;

      if (!ACTIVE_STATUSES.has(status.status)) {
        const [rows, codebookDetail] = await Promise.all([getRunResults(runId), getCodebook(codebookId)]);
        if (isStale(token)) return;
        setResults(rows);
        setCodebookLabels(codebookDetail.spec.categories.map((c) => c.label));
      }
    } catch (err) {
      if (isStale(token)) return;
      if (pollRef.current) {
        // A transient failure (network blip, brief backend hiccup) during
        // an already-established poll must not kill polling for a run
        // that's still actually running -- skip this tick silently and
        // let the next interval fire retry. Only the *initial* load (no
        // interval established yet) surfaces the error, since without an
        // interval nothing would ever recover on its own.
        return;
      }
      stopPolling();
      setError(err);
    }
  }

  function selectRun(run: RunSummary) {
    setError(null);
    stopPolling();
    selectionTokenRef.current += 1;
    const token = selectionTokenRef.current;
    setSelectedRunId(run.id);
    setSelectedStatus(null);
    setResults(null);
    setCodebookLabels([]);
    loadRunDetail(run.id, run.codebook_id, token);
  }

  function startNewRun() {
    setError(null);
    stopPolling();
    selectionTokenRef.current += 1;
    setSelectedRunId(null);
    setSelectedStatus(null);
    setResults(null);
  }

  async function handleCreated(runId: number) {
    try {
      const runList = await listRuns();
      setRuns(runList);
      const run = runList.find((r) => r.id === runId);
      if (run) {
        selectRun(run);
      } else {
        // Should be unreachable -- POST /runs commits the RunRecord before
        // returning run_id, so the very next listRuns() should always see
        // it. Surfacing an error instead of silently no-op'ing if it ever
        // isn't makes that assumption visible rather than leaving the user
        // staring at a run list that doesn't show the run they just
        // started, with no explanation.
        setError(new Error(`run ${runId} was created but not found in the run list`));
      }
    } catch (err) {
      setError(err);
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

      <div className="runs-layout">
        <section className="card">
          <h2 className="card-title">{t("runs.listTitle")}</h2>
          <button type="button" className="btn btn-ghost" onClick={startNewRun}>
            {t("runs.newRun")}
          </button>
          {runs.length === 0 ? (
            <p className="empty-state">{t("runs.none")}</p>
          ) : (
            <ul className="codebook-list">
              {runs.map((r) => (
                <li key={r.id}>
                  <button type="button" onClick={() => selectRun(r)}>
                    #{r.id} {r.codebook_name} · {r.corpus_id} <span className="pill">{r.status}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <div className="card">
          {selectedRunId === null && (
            <RunForm corpora={corpora} codebooks={codebooks} onCreated={handleCreated} onError={setError} />
          )}

          {selectedRunId !== null && selectedStatus && ACTIVE_STATUSES.has(selectedStatus.status) && (
            <div>
              <h3 className="card-title">{t("runs.inProgress")}</h3>
              <div className="progress-track">
                <div
                  className="progress-fill"
                  style={{
                    width:
                      selectedStatus.total > 0
                        ? `${(selectedStatus.processed / selectedStatus.total) * 100}%`
                        : "0%",
                  }}
                />
              </div>
              <p className="empty-state">
                {selectedStatus.processed} / {selectedStatus.total}
              </p>
            </div>
          )}

          {selectedRunId !== null && selectedStatus?.status === "error" && (
            <div className="banner-error">{t("runs.runFailed")}</div>
          )}

          {selectedRunId !== null && results && (
            <ResultsTable
              runId={selectedRunId}
              results={results}
              codebookLabels={codebookLabels}
              onResultsChange={(updater) => setResults((prev) => (prev ? updater(prev) : prev))}
              onError={setError}
            />
          )}
        </div>
      </div>
    </div>
  );
}
