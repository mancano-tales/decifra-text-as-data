# Research Materials & Literature Index — Cifra (`cifra-text-as-data`)

*Date: September 1, 2026*  
*Target Application:* Cifra (`cifra-text-as-data`)

This directory catalogs primary research papers, literature reviews, codebase deep dives, and empirical pilot datasets supporting the development of **Cifra**.

---

## 1. Primary Research Papers & Preprints

### A. Halterman & Keith (2025) — "Codebook LLMs"
- **File**: `2407.10747v2.pdf` (arXiv:2407.10747v2, Jan 2025)
- **Title**: *Codebook LLMs: Evaluating LLMs as Measurement Tools for Political Science Concepts*
- **Authors**: Andrew Halterman (Michigan State Univ) & Katherine A. Keith (Williams College)
- **Summary**: Introduces the foundational five-stage framework for operationalizing social science codebooks into LLMs, highlighting construct validity risks and behavioral testing.
- **Detailed Dialogue**: [`2026-09-01_halterman_keith_codebook_llms_dialogue_and_cifra.md`](2026-09-01_halterman_keith_codebook_llms_dialogue_and_cifra.md)

### A2. Halterman & Keith (2026) — "What is a protest anyway?"
- **Title**: *What is a protest anyway? Codebook conceptualization is still a first-order concern in LLM-era classification*
- **Venue**: ACL 2026 (Proceedings of the 64th Annual Meeting of the ACL, Volume 1: Long Papers, pp. 2043–2059)
- **Authors**: Andrew Halterman (Michigan State Univ) & Katherine A. Keith (Williams College)
- **Summary**: Conceptual/theoretical follow-up (no new benchmark). Decomposes annotation error into conceptualization error (incomplete codebook) vs. scoring error (misapplied codebook), shows via simulation that conceptualization-induced bias survives both a more accurate LLM and post-hoc bias-correction methods (PPI, DSL), and recommends a "pragmatist" workflow combining a full codebook, LLM labels on the full corpus, a small gold subset, and PPI/DSL correction.
- **Not committed to this repo** (copyrighted, published paper; the original PDF lives in the author's own Drive) — see the dialogue doc for why.
- **Detailed Dialogue**: [`2026-09-08_halterman_keith_protest_anyway_dialogue_and_decifra.md`](2026-09-08_halterman_keith_protest_anyway_dialogue_and_decifra.md)

### A3. Mercês et al. (2026) — "LLMs in Deductive Coding" (SBES)
- **Title**: *Investigating the use of LLMs in Deductive Coding within the Context of Software Engineering*
- **Venue**: SBES 2026 (CBSoft, IME-USP), Research Track, Sept 9 2026
- **Authors**: Samuel Mercês, Moaath Alshaikh, Gabriel Cordeiro Moraes, Lucca de Almeida Hora Coutinho, Glauco de Figueiredo Carneiro, Manoel Mendonça, José Amancio Macedo Santos (UEFS / UFBA / UFS)
- **Open PDF**: `https://cbsoft.sbc.org.br/2026/data/papers/sbes/Investigating the use of LLMs in Deductive Coding within the Context of Software Engineering.pdf`
- **Summary**: Applies Decifra's core empirical question in another domain (Empathy in SE): can an LLM apply a pre-existing 54-code codebook faithfully? Contributes a reusable five-category agreement/divergence taxonomy, an "Excessive Granularity Bias" finding that scales with codebook size (LLM over-assignment ~28% at 6 codes → ~57% at 15 codes), and a counterintuitive one-shot-beats-few-shot result. Reports no Cohen's kappa and no per-category precision/recall/F1.
- **Detailed Comparison**: [`2026-09-08_sbes_deductive_coding_and_annotaise_comparison.md`](2026-09-08_sbes_deductive_coding_and_annotaise_comparison.md)

### A4. Lopes et al. (2026) — AnnotAISE (SBES Tools)
- **Title**: *AnnotAISE: Web-Based Data Annotation Platform For Software Engineering Research*
- **Venue**: SBES 2026 (CBSoft, IME-USP), Tools Track, Sept 10 2026
- **Authors**: João Paulo Lopes, Bruno T. Fernandes, Beatriz Ritter, Daniel Coutinho, Robbie Carvalho, Alessandro Garcia, Juliana Alves Pereira (PUC-Rio)
- **Software**: [`github.com/aisepucrio/annotaise`](https://github.com/aisepucrio/annotaise) (MIT; Django + Next.js + PostgreSQL + Docker Compose)
- **Summary**: The closest sibling *software* to Decifra that currently exists, built in deliberately opposite directions: its codebook equivalent is an unstructured free-text Markdown guideline, and the LLM enters only as a post-hoc tiebreaker (local models via Ollama) rather than as the coder. Evaluated with TAM (28 participants) — perceived usability, not annotation quality, as the authors concede. Useful to Decifra as a **complementary** gold-label collection tool, not a competitor.
- **Detailed Comparison**: [`2026-09-08_sbes_deductive_coding_and_annotaise_comparison.md`](2026-09-08_sbes_deductive_coding_and_annotaise_comparison.md)

### B. DATALUTA News Automation Paper (NERA/UNESP, 2025/2026)
- **Title**: *O Banco de Dados da Luta pela Terra (DATALUTA): Automatização de Coleta e Registro de Notícias*
- **Authors**: NERA / UNESP (Sobreiro Filho et al., 2025/2026)
- **Summary**: Documents the field-by-field automated pipeline for coding news articles into ~25 agrarian conflict variables using BeautifulSoup, SpaCy NER, RAG, and fine-tuned BERTimbau-large models.
- **Detailed Analysis**: [`2026-09-01_dataluta_paper_analysis_and_cifra_synergy.md`](2026-09-01_dataluta_paper_analysis_and_cifra_synergy.md)

---

## 2. Research Reports & Codebase Deep Dives

| Document | Focus & Scope |
| :--- | :--- |
| **[`2026-08-31_llm_text_coding_literature_and_landscape.md`](2026-08-31_llm_text_coding_literature_and_landscape.md)** | Ecosystem survey across Python ML frameworks, R CSS packages, CAQDAS tools, and top Political Science papers (*Political Analysis*, *APSR*, *PNAS*, *ACL*). |
| **[`2026-08-31_codebase_deep_dive_and_benchmarks.md`](2026-08-31_codebase_deep_dive_and_benchmarks.md)** | Line-by-line inspection of 7 cloned reference repos (`deepseek-harness`, `quallmer`, `autolabel`, `instructor`, `codebook-lab`, `potato`, `LLM4Humanities`). |
| **[`2026-08-31_adversarial_codebase_audit_and_pitfalls.md`](2026-08-31_adversarial_codebase_audit_and_pitfalls.md)** | Zero-happy-path adversarial failure mode analysis and 5 real-world edge-case mitigations for Cifra (SQLite WAL, Windows encoding, etc.). |
| **[`2026-09-01_dataluta_paper_analysis_and_cifra_synergy.md`](2026-09-01_dataluta_paper_analysis_and_cifra_synergy.md)** | Empirical analysis of the NERA/UNESP DATALUTA paper, BERTimbau limitations, and Cifra orchestration synergy. |
| **[`2026-09-01_halterman_keith_codebook_llms_dialogue_and_cifra.md`](2026-09-01_halterman_keith_codebook_llms_dialogue_and_cifra.md)** | Detailed dialogue with Halterman & Keith (2025) mapping Stage 0–4 framework onto Cifra's architecture. |
| **[`2026-09-08_halterman_keith_protest_anyway_dialogue_and_decifra.md`](2026-09-08_halterman_keith_protest_anyway_dialogue_and_decifra.md)** | Dialogue with Halterman & Keith (2026, ACL) on conceptualization vs. scoring error; identifies that Decifra's Validation screen currently has no way to detect conceptualization error, and proposes a concrete PPI-corrected prevalence estimator as the highest-value addition. |
| **[`2026-09-08_sbes_deductive_coding_and_annotaise_comparison.md`](2026-09-08_sbes_deductive_coding_and_annotaise_comparison.md)** | Three-way maturity and quality comparison of Mercês et al. (SBES 2026), Halterman & Keith (ACL 2026), and AnnotAISE. Establishes that none of the three does what Decifra proposes: H&K describe the workflow but ship no code and explicitly caution against automating codebook *conceptualization*; Mercês et al. hand-roll Decifra's engine for one study and recommend guidelines instead of a tool; AnnotAISE builds durable software for the opposite half of the problem. Yields three constraints for Decifra (documented limit on Codebook Editor automation; measure over-coding before shipping R1.1 multi-label; make prompt example count a run parameter). |
| **[`2026-09-02_state_of_the_project_diagnosis_and_distribution.md`](2026-09-02_state_of_the_project_diagnosis_and_distribution.md)** | Critical diagnosis of the MVP as built vs. the general-purpose product vision, distribution-path cost comparison (pipx / PyInstaller+pywebview / Tauri / hosted), recommended build order, and trajectory risks. Feeds [`docs/ROADMAP.md`](../ROADMAP.md). |

---

## 3. Real-World Pilot Datasets

1. **`Reforming-TE-PT` (Bayesian Process Tracing Workbook V7)**:
   - Source: `Reforming-TE-PT/v7_banco_process_tracing_baesiano_abdutivo_manual.xlsx`
   - Content: Folha articles (1990s–2010s) evaluated on a 7-level verbal probability scale across competing hypothesis pairs ($H_1, H_2$).
   - Integration script: `examples/reforming_te_pt/load_pilot.py`

2. **DATALUTA Agrarian Conflict Corpus (NERA/UNESP)**:
   - Source: Historical news spreadsheets (2021–2023) covering land occupations, action scales, and UN SDGs (ODS 1–17).
