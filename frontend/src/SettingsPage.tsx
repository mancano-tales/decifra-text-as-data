import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { getSettings, putSettings } from "./api";
import type { Settings } from "./api";
import { describeApiError } from "./errorMessages";

export function SettingsPage() {
  const {t} = useTranslation();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [keys, setKeys] = useState<Record<string,string>>({});
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => { let active = true; getSettings().then(s => {if(active) setSettings(s);}).catch(e => {if(active) setError(e);}); return () => {active=false;}; }, []);
  const message = error ? describeApiError(error,t) : null;
  return <section className="card">
    <h2>{t("settings.title")}</h2>
    {message && <div className="banner-error">{message.message}<p>{message.detail}</p></div>}
    {!settings ? <p>{t("settings.loading")}</p> : <form onSubmit={async e => {
      e.preventDefault(); setBusy(true); setError(null); setSaved(false);
      try {setSettings(await putSettings(settings, keys)); setKeys({}); setSaved(true);} catch(e) {setError(e);} finally {setBusy(false);}
    }}>
      <p>{t("settings.help")}</p>
      <div className="field"><label htmlFor="settings-mode">{t("runs.providerMode")}</label><select id="settings-mode" value={settings.provider_mode} onChange={e=>setSettings({...settings,provider_mode:e.target.value as Settings["provider_mode"]})}><option value="cli">CLI</option><option value="api_key">API</option></select></div>
      <div className="field"><label htmlFor="settings-model">{t("runs.model")}</label><input id="settings-model" value={settings.model} onChange={e=>setSettings({...settings,model:e.target.value})}/></div>
      <div className="field"><label htmlFor="settings-cli">{t("runs.cliCommand")}</label><input id="settings-cli" value={settings.cli_command} onChange={e=>setSettings({...settings,cli_command:e.target.value})}/></div>
      <div className="field"><label htmlFor="settings-prompt">{t("runs.cliPromptMode")}</label><select id="settings-prompt" value={settings.cli_prompt_mode} onChange={e=>setSettings({...settings,cli_prompt_mode:e.target.value as "stdin"|"arg"})}><option value="stdin">stdin</option><option value="arg">arg</option></select></div>
      <p>{t("settings.keyHelp")}</p>
      {["anthropic","openai"].map(v => <div className="field" key={v}><label htmlFor={`key-${v}`}>{v} — {t(settings.credentials[v]?.configured ? "settings.configured" : "settings.missing")} ({settings.credentials[v]?.source})</label><input id={`key-${v}`} type="password" autoComplete="new-password" value={keys[`${v}_api_key`] ?? ""} onChange={e=>setKeys({...keys,[`${v}_api_key`]:e.target.value})}/><button type="button" className="btn-ghost" onClick={()=>setKeys({...keys,[`${v}_api_key`]:""})}>{t("settings.removeKey")}</button>{keys[`${v}_api_key`] === "" && <small>{t("settings.removePending")}</small>}</div>)}
      <h3>{t("settings.estimate")}</h3><p>{t("settings.priceHelp")}</p>
      <div className="field"><label htmlFor="output-budget">{t("settings.outputBudget")}</label><input id="output-budget" type="number" min="1" max="32000" required value={settings.output_tokens_per_document} onChange={e=>setSettings({...settings,output_tokens_per_document:Number(e.target.value)})}/></div>
      {(["input_usd_per_million","output_usd_per_million"] as const).map(k=><div className="field" key={k}><label htmlFor={k}>{t(`settings.${k}`)}</label><input id={k} type="number" min="0" step="any" value={settings[k] ?? ""} onChange={e=>setSettings({...settings,[k]:e.target.value===""?null:Number(e.target.value)})}/></div>)}
      <button className="btn btn-primary" disabled={busy}>{t("runs.save")}</button>
      {saved && <p role="status">{t("settings.saved")}</p>}
    </form>}
  </section>;
}
