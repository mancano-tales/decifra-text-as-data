import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { createRun, estimateRun, getSettings } from "./api";
import type { CodebookSummary, CorpusSummary, RunEstimate, Settings } from "./api";

function parseCliCommand(raw: string): string[] {
  // A naive `.split(" ")` breaks any command containing a double-quoted
  // argument or a quoted path with spaces (e.g. `"C:\Program
  // Files\nodejs\claude.cmd" -p` or `agy -p --prompt "foo bar"`), handing
  // the backend a mangled argv that subprocess.run can't exec. This
  // recognizes double-quoted segments as single tokens (quotes stripped)
  // and splits everything else on whitespace -- not a full shell parser
  // (no escaped quotes, no single quotes), but covers the common case.
  const tokens: string[] = [];
  const pattern = /"([^"]*)"|(\S+)/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(raw)) !== null) {
    tokens.push(match[1] !== undefined ? match[1] : match[2]);
  }
  return tokens;
}

interface RunFormProps {
  corpora: CorpusSummary[];
  codebooks: CodebookSummary[];
  onCreated: (runId: number) => Promise<void>;
  onError: (err: unknown) => void;
}

export function RunForm({ corpora, codebooks, onCreated, onError }: RunFormProps) {
  const { t } = useTranslation();
  const [corpusId, setCorpusId] = useState("");
  const [codebookId, setCodebookId] = useState("");
  const [model, setModel] = useState("");
  const [providerMode, setProviderMode] = useState<"api_key" | "cli">("api_key");
  const [cliCommand, setCliCommand] = useState("claude -p");
  const [cliPromptMode, setCliPromptMode] = useState<"stdin" | "arg">("stdin");
  const [defaults, setDefaults] = useState<Settings | null>(null);
  const [bypassCache, setBypassCache] = useState(false);
  const [estimate, setEstimate] = useState<{key:string; value:RunEstimate} | null>(null);
  useEffect(() => { let active=true; getSettings().then(s=>{if(!active) return; setDefaults(s); setModel(s.model); setProviderMode(s.provider_mode); setCliCommand(s.cli_command); setCliPromptMode(s.cli_prompt_mode);}).catch(onError); return ()=>{active=false;}; }, [onError]);
  const request = {codebook_id:Number(codebookId), corpus_id:corpusId, model:model.trim(), provider_mode:providerMode, bypass_cache:bypassCache, ...(providerMode === "cli" ? {cli_command:parseCliCommand(cliCommand),cli_prompt_mode:cliPromptMode}: {})};
  const requestKey=JSON.stringify(request);
  const currentEstimate=estimate?.key === requestKey ? estimate.value : null;
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (submitting) return;
    const trimmedModel = model.trim();
    if (!trimmedModel) {
      onError(new Error(t("runs.modelRequired")));
      return;
    }
    const commandParts = parseCliCommand(cliCommand);
    if (providerMode === "cli" && commandParts.length === 0) {
      onError(new Error(t("runs.cliCommandRequired")));
      return;
    }
    setSubmitting(true);
    try {
      if (!currentEstimate) {
        const value=await estimateRun(request); setEstimate({key:requestKey,value}); return;
      }
      const { run_id } = await createRun(request);
      await onCreated(run_id);
    } catch (err) {
      onError(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <h3 className="card-title">{t("runs.newRun")}</h3>
      <div className="field">
        <label className="field-label" htmlFor="run-corpus">
          {t("runs.corpus")}
        </label>
        <select id="run-corpus" value={corpusId} onChange={(e) => setCorpusId(e.target.value)} required>
          <option value="" disabled>
            {t("runs.selectCorpus")}
          </option>
          {corpora.map((c) => (
            <option key={c.corpus_id} value={c.corpus_id}>
              {c.corpus_id} ({c.document_count})
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label className="field-label" htmlFor="run-codebook">
          {t("runs.codebook")}
        </label>
        <select id="run-codebook" value={codebookId} onChange={(e) => setCodebookId(e.target.value)} required>
          <option value="" disabled>
            {t("runs.selectCodebook")}
          </option>
          {codebooks.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label className="field-label" htmlFor="run-model">
          {t("runs.model")}
        </label>
        <input id="run-model" value={model} onChange={(e) => setModel(e.target.value)} required />
      </div>
      <div className="field">
        <label className="field-label" htmlFor="run-provider-mode">
          {t("runs.providerMode")}
        </label>
        <select
          id="run-provider-mode"
          value={providerMode}
          onChange={(e) => setProviderMode(e.target.value as "api_key" | "cli")}
        >
          <option value="api_key">{t("runs.providerApiKey")}</option>
          <option value="cli">{t("runs.providerCli")}</option>
        </select>
      </div>
      {providerMode === "cli" && (
        <>
          <div className="field">
            <label className="field-label" htmlFor="run-cli-command">
              {t("runs.cliCommand")}
            </label>
            <input id="run-cli-command" value={cliCommand} onChange={(e) => setCliCommand(e.target.value)} required />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="run-cli-prompt-mode">
              {t("runs.cliPromptMode")}
            </label>
            <select
              id="run-cli-prompt-mode"
              value={cliPromptMode}
              onChange={(e) => setCliPromptMode(e.target.value as "stdin" | "arg")}
            >
              <option value="stdin">stdin</option>
              <option value="arg">arg</option>
            </select>
          </div>
        </>
      )}
      <label><input type="checkbox" checked={bypassCache} onChange={e=>setBypassCache(e.target.checked)}/>{t("runs.bypassCache")}</label>
      {!defaults && <p>{t("settings.loading")}</p>}
      {providerMode === "api_key" && defaults && !Object.values(defaults.credentials).some(c=>c.configured) && <p>{t("runs.configureFirst")}</p>}
      {currentEstimate && <section className="estimate-panel" role="status">
        <h4>{t("runs.estimateTitle")}</h4>
        <p>{t("runs.estimateCounts",currentEstimate as unknown as Record<string,unknown>)}</p>
        <p>{t("runs.estimateTokens",currentEstimate as unknown as Record<string,unknown>)}</p>
        <p>{currentEstimate.estimated_usd === null ? t("runs.priceUnavailable") : t("runs.estimatePrice",{price:currentEstimate.estimated_usd.toFixed(4)})}</p>
        <small>{t("runs.estimateDisclaimer")}</small>
      </section>}
      <button type="submit" className="btn btn-primary" disabled={submitting || !defaults}>
        {t(currentEstimate ? "runs.start" : "runs.estimateButton")}
      </button>
    </form>
  );
}
