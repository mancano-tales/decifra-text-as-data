import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CodebookEditor } from "./CodebookEditor";
import { CorpusPage } from "./CorpusPage";
import { RunsPage } from "./RunsPage";

import { SettingsPage } from "./SettingsPage";

type Tab = "corpus" | "codebook" | "runs" | "settings";

function App() {
  const { t, i18n } = useTranslation();
  const [tab, setTab] = useState<Tab>("corpus");

  return (
    <>
      <header className="app-header">
        <div className="brand">
          <img className="brand-mark" src="/favicon.png" alt="Decifra" width="36" height="36" />
          <span className="app-title">{t("app.title")}</span>
          <span className="app-tagline">{t("app.tagline")}</span>
        </div>
        <div className="header-controls">
          <div className="seg">
            <button className="seg-btn" disabled={tab === "corpus"} onClick={() => setTab("corpus")}>
              {t("app.nav.corpus")}
            </button>
            <span className="seg-sep" />
            <button className="seg-btn" disabled={tab === "codebook"} onClick={() => setTab("codebook")}>
              {t("app.nav.codebook")}
            </button>
            <span className="seg-sep" />
            <button className="seg-btn" disabled={tab === "runs"} onClick={() => setTab("runs")}>
              {t("app.nav.runs")}
            </button>
            <button className="seg-btn" disabled={tab === "settings"} onClick={() => setTab("settings")}>{t("settings.title")}</button>
          </div>
          <div className="seg" aria-label="Language">
            <button
              className="seg-btn"
              disabled={i18n.resolvedLanguage === "pt-BR"}
              onClick={() => i18n.changeLanguage("pt-BR")}
            >
              PT
            </button>
            <span className="seg-sep" />
            <button
              className="seg-btn"
              disabled={i18n.resolvedLanguage === "en"}
              onClick={() => i18n.changeLanguage("en")}
            >
              EN
            </button>
          </div>
        </div>
      </header>
      <main className="app-main">
        {tab === "corpus" && <CorpusPage />}
        {tab === "codebook" && <CodebookEditor />}
        {tab === "runs" && <RunsPage />}
        {tab === "settings" && <SettingsPage />}
      </main>
    </>
  );
}

export default App;
