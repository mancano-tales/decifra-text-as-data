# Three-way comparison: Mercês et al. (SBES 2026), Halterman & Keith (ACL 2026), and AnnotAISE — and where Decifra sits

*Date: September 8, 2026*
*Target application:* Decifra (`cifra-text-as-data`)

**Sources read in full for this document:**

1. **Mercês et al. (2026)** — *Investigating the use of LLMs in Deductive Coding within the Context of Software Engineering*. SBES 2026 Research Track. Samuel Mercês, Moaath Alshaikh, Gabriel Cordeiro Moraes, Lucca de Almeida Hora Coutinho, Glauco de Figueiredo Carneiro, Manoel Mendonça, José Amancio Macedo Santos (UEFS / UFBA / UFS). Openly published by the conference at
   `https://cbsoft.sbc.org.br/2026/data/papers/sbes/Investigating the use of LLMs in Deductive Coding within the Context of Software Engineering.pdf`
   (~10,457 words extracted).
2. **Halterman & Keith (2026)** — *What is a protest anyway? Codebook conceptualization is still a first-order concern in LLM-era classification*. ACL 2026, Long Papers, pp. 2043–2059. Read from the author's own copy (17 pages, ~10,493 words extracted via `pypdf`). Already the subject of
   [`2026-09-08_halterman_keith_protest_anyway_dialogue_and_decifra.md`](2026-09-08_halterman_keith_protest_anyway_dialogue_and_decifra.md); this document adds the direct comparison and verifies that earlier summary against the original text (it holds up).
3. **AnnotAISE (Lopes et al. 2026)** — *AnnotAISE: Web-Based Data Annotation Platform For Software Engineering Research*. SBES 2026 Tools Track. João Paulo Lopes, Bruno T. Fernandes, Beatriz Ritter, Daniel Coutinho, Robbie Carvalho, Alessandro Garcia, Juliana Alves Pereira (PUC-Rio). Paper from the conference site (6 pages); repository and README from
   [`github.com/aisepucrio/annotaise`](https://github.com/aisepucrio/annotaise) (MIT).

As with the other dialogue documents in this directory, this is original analysis in my own words. No full text of any of the three papers is committed here. Short attributed quotations only.

---

## 1. Why these three together

The author found the CBSoft 2026 programme (IME-USP, Sept 8–11) and asked which of it matters for Decifra. Two SBES papers turned out to sit directly on Decifra's problem, from opposite sides:

- **Mercês et al.** asks Decifra's core empirical question — *can an LLM apply a pre-existing codebook faithfully?* — in a different domain (Empathy in Software Engineering rather than political science).
- **AnnotAISE** builds the closest sibling *software* to Decifra that currently exists, and resolves several of the same design problems in deliberately opposite directions.

Halterman & Keith (2026) is the theoretical anchor Decifra already uses. Reading all three at once makes the position Decifra occupies unusually legible, because between them they cover the theory, the empirical test, and the tooling — and none of the three does what Decifra proposes to do.

---

## 2. Maturity and quality assessment

Three different genres, so the comparison is by axis rather than by a single score.

| | Halterman & Keith (2026) | Mercês et al. (2026) | AnnotAISE (2026) |
| :--- | :--- | :--- | :--- |
| Venue | ACL Long Paper | SBES Research Track | SBES Tools Track |
| Genre | Conceptual / methodological | Exploratory empirical | Tool paper |
| Core evidence | Simulation + 4 real in-production codebooks compared on 9 dimensions | 1 model, 1 domain, 238 excerpts, 54 codes | TAM survey, 28 participants |
| Central metric | Estimator bias (formal) | Ad-hoc weighted accuracy index | 5-point Likert perception scores |
| Released artifact | **None found** | Replication package (cited) | MIT software + Docker + Zenodo DOI |
| Maturity | High | Medium | High as engineering, low as evaluation |

### 2.1 Halterman & Keith (2026) — strongest of the three, with one irony

The rigour is not close. The decomposition of annotation error into *conceptualization error* (incomplete codebook) and *scoring error* (misapplied codebook) is formally clean and genuinely load-bearing. Figure 2 — four real production PROTEST codebooks (ACE, ACLED, CAMEO, Crowd Counting Consortium) disagreeing with one another across nine dimensions — is field evidence, not a thought experiment. The §5 simulation isolates the claim that matters: under an incomplete codebook the bias-corrected estimate is biased **at every LLM error rate, including zero**.

They are honest where it counts. Both proposed completeness standards are explicitly flagged as not fully complete and marked as future work. Which post-hoc correction method performs best in finite samples is stated as an open problem.

**The irony worth recording:** the paper that specifies PPI in closed form (Algorithm 1) and recommends a concrete "pragmatist" workflow **ships no code of its own**. A search of the full text turns up no GitHub, Zenodo, or OSF release by the authors — the only replication material mentioned is a third party's, in a footnote. A paper that says "do it this way" and does not provide the implementation is describing exactly the gap Decifra can fill.

### 2.2 Mercês et al. (2026) — real contribution, weak measurement apparatus

**The genuine contribution is the five-category taxonomy** of agreement and divergence: Full Agreement, Equivalent Coding with Expansion, Valid Interpretive Divergence, Superior Human Coding, Superior LLM Coding. Two researchers independently assigned categories with a consensus cycle. This is reusable, and it does something Cohen's kappa cannot: it distinguishes an LLM being *wrong* from an LLM being *differently right*.

Two findings are directly useful to Decifra:

- **"Excessive Granularity Bias."** The model prioritises exhaustivity over interpretive parsimony. Crucially, the effect scales with codebook size: Equivalent Coding with Expansion by the LLM was ~28% in Barriers (6 codes), 56.58% in Practice (15 codes), and 54.54% in Effects (28 codes). Full Agreement collapsed correspondingly — 40.63% → 11.84% → 10.39%.
- **One-shot beat few-shot**, counter to the usual assumption. In the Meaning dimension, adding examples raised the Superior Human Coding (i.e. failure) rate from 15.09% to 25.00%. Their explanation is overfitting to the surface form of the examples at the expense of the abstract definition in the codebook.

**Where a top-venue referee would push back:**

1. **No Cohen's kappa.** No chance correction, no per-category precision/recall/F1. They report raw agreement (77.23%, 68.91%, 45.18%, 45.29%) on a multi-label task with up to 28 codes, where raw agreement is close to uninterpretable. They cite Xiao et al.'s κ = 0.61 and Bijker et al.'s κ = 0.56–0.73 in their own Related Work, so the standard was known and not applied.
2. **Equation 1 is truncated in the published PDF** — the variables were dropped in typesetting, so the reader cannot reconstruct the metric that carries the quantitative results.
3. **No repeated-run reliability test.** RQ2 is about consistency, but each prompt was run once, with hyperparameters left at defaults (temperature not set near zero), and "strong deterministic convergence" is supported by qualitatively comparing the wording of two justifications. That is not a measure of self-consistency.
4. **n = 1 model (Gemini 2.5 Pro), n = 1 domain, n = 1 corpus** (22 DEV.to articles). All three are acknowledged as threats to validity.
5. **Few-shot missing for half the design.** It was infeasible for Practice and Effects, so RQ2 is answered on two of four dimensions.
6. **Partial circularity.** The codebook was inductively derived by Cerqueira et al. from the same transcripts the LLM then reads. Named as a construct-validity threat and mitigated rhetorically, not empirically.

There is also a rhetorical move to watch: reclassifying 55.84% of the Effects dimension as "Equivalent Coding with Expansion" rather than error is defensible, but it is also the move that converts 45% accuracy into a positive result.

### 2.3 AnnotAISE — mature software, evaluation that does not measure the thing that matters

The software is serious: Django REST + Next.js/TypeScript, Docker Compose, PostgreSQL, nginx, GitHub Actions CI, MIT licence, Zenodo DOI, a bilingual in-app guide (PT/EN), and real use by three other papers from the group (Oliveira et al. ×2 on code smells; Canuto et al. on emotion in agile meetings). This is a level of engineering maturity Decifra does not yet have.

The evaluation is the weak half, and the authors say so themselves in Future Work: the study "assesses perceived usability rather than the quality of the resulting annotations." TAM measures perceived ease of use, perceived usefulness, and intention to use — none of which is annotation quality. Compounding factors:

- 76.2% of annotators were undergraduates; 42.9% had no prior familiarity with annotation at all.
- **No administrator (n = 7) had previously used a dedicated annotation platform.** "Better than what I know" therefore means "better than a spreadsheet or a Google Form."
- The two lowest-scoring items are CSV import (μ = 3.00) and configuring data fields and questions (μ = 3.43) — by their own data, project setup is the friction point.
- The LLM tie-breaker scored μ = 3.00 and is reported as inconclusive rather than negative.

**Artifact nit:** the README cites `10.5281/zenodo.20388574` while the paper's Artifact Availability section cites `10.5281/zenodo.21462965`. Probably different versions; worth resolving before citing either.

---

## 3. The question that matters most: does anyone propose automating codebook *production*?

Decifra's product vision automates the mechanical coding step while insisting the researcher designs the codebook. It is worth knowing whether the literature anticipates a tool that goes further.

### 3.1 Halterman & Keith: yes — they know the category exists, and publish a caution

§3.4 cites four works proposing to incorporate LLMs into codebook conceptualization itself (Dai et al. 2023; Gao et al. 2023; Xiong et al. 2025; Zhong et al. 2025). Their assessment grants the upside — less analyst time, potential surfacing of edge cases — and then lands the warning:

> "Whether LLM-assisted codebooks overinflate analysts' confidence in the 'completeness' of their codebooks is also an open question."

They also note that evaluating such approaches properly would require collecting expert labels across several *versions* of a codebook — an evaluation nobody has run.

The conclusion reinforces it: LLMs cannot replace the consensus of a community of peer experts on whether a codebook is complete, so human domain expertise should be heavily incorporated into early pilot rounds of codebook creation.

And §3.6 is titled, flatly, **"Conceptualization is not prompt engineering"** — a direct warning against precisely the conflation that a polished tool can induce.

### 3.2 Mercês et al.: no

They never propose software. Their stated future work is "a definitive version of guidelines for deductive coding with LLMs" — a document, not a tool.

Note what that implies. They built Python automation scripts, Gemini API integration, a six-component prompt architecture (persona, RQ context, codebook definitions, scope instructions, structured output format with mandatory justification, examples), and structured-output parsing — used it once and discarded it. That is Decifra's engine, hand-rolled per study. The market gap appears here in the negative.

Their prompt architecture is also worth comparing to Decifra's directly: components (1)–(3) and (6) map onto `Codebook.to_prompt()`, and (5) — mandatory justification — is Decifra's `justificativa` / `rationale` field. Independent convergence on the same design is mild evidence the design is right.

### 3.3 AnnotAISE: no, and deliberately the inverse

AnnotAISE's equivalent of a codebook is the **annotation guideline**: a free-text Markdown document with no structure at all. No per-category definitions, no positive/negative examples, no boundary notes. It is a reference the human annotator reads, not an instrument the system reasons over.

And the LLM enters only as a **tiebreaker** after human annotators deadlock — four local models via Ollama (`llama3.1:8b`, `llama3.2:3b`, `qwen2.5:7b`, `mistral-nemo:12b`; a code-oriented pool of three for code contexts), voting, with the answer discarded unless it string-matches a valid option. The LLM never codes the corpus.

This is the exact inverse of Decifra: **AnnotAISE automates the human coding workflow; Decifra automates the coding.**

---

## 4. What this means for Decifra

### 4.1 What is validated

- **The Type III codebook schema is the right call and now has triangulated support.** `definition` + `positive_examples` + `negative_examples` + `boundary_notes` (see `validate_spec()` and `Codebook.to_prompt()` in [`codebook.py`](../../src/text_as_data/codebook.py)) is what Halterman & Keith say most substantive applications require, and it is exactly what AnnotAISE's free-text guideline lacks.
- **The Validation screen's metric set is ahead of the published empirical work.** `agreement_report()` in [`validation.py`](../../src/text_as_data/validation.py) already computes accuracy, Cohen's kappa, and per-category precision/recall/F1 via `scikit-learn`, plus a disagreement list. Mercês et al. — a peer-reviewed research-track paper on this exact task — reports none of that.
- **Nobody has shipped the estimator.** The PPI recommendation from Halterman & Keith remains unimplemented in any tool found so far, which reinforces recommendation #1 of the earlier dialogue doc.

### 4.2 Three concrete constraints, in priority order

1. **The §3.4 warning is about Decifra's Codebook Editor, specifically.** If the editor ever suggests categories or auto-drafts `boundary_notes`, Decifra walks into the failure mode Halterman & Keith flag: inflated analyst confidence in completeness. `AGENTS.md`'s existing rule — the researcher designs the codebook, and the Codebook Editor is the most important screen in the software — should be promoted from a product decision to a **documented methodological constraint with this citation attached**. This costs nothing now and prevents a plausible future feature request from quietly breaking the tool's scientific claim.

2. **"Excessive Granularity Bias" is a testable prediction about Decifra's own output, and it lands on R1.1.** The current schema is single-label (a `categoria` enum), which structurally avoids the problem. The draft multi-variable codebook design in [`docs/superpowers/specs/2026-09-02-r1.1-multi-variable-codebooks-design.md`](../superpowers/specs/2026-09-02-r1.1-multi-variable-codebooks-design.md) walks straight into it. Mercês et al. supply the expected magnitudes: LLM over-assignment rising from ~28% at 6 codes to ~57% at 15 codes, with Full Agreement falling from ~41% to ~12%. **Recommendation: measure this on the V7 pilot before shipping multi-label, not after.** That spec is still awaiting the author's sign-off, so this is the right moment to add the measurement to it.

3. **One-shot over few-shot is a cheap, testable default.** Decifra currently passes all `positive_examples` from the codebook into the prompt. Mercês et al. found that adding examples *increased* the failure rate, because the model overfits the examples' surface form instead of applying the abstract definition. This is directly checkable against the V7 pilot data, and if it replicates, the number of examples injected into the prompt should become a run parameter rather than "all of them."

### 4.3 Distribution: no answer available to copy

AnnotAISE solves distribution the way Decifra explicitly rejected: Docker Compose + PostgreSQL + nginx, a shared server, two user roles, ~5 GB of disk and Docker Desktop as a prerequisite. That works for a lab with infrastructure. It does not work for the lone social scientist on a laptop, who is Decifra's user.

This is worth recording as a finding rather than a disappointment: **the closest comparable tool, built by a well-resourced group (PUC-Rio, Alessandro Garcia's lab, with CAPES/CNPq/FAPESP/FAPEMIG funding), did not solve the non-developer distribution problem either — it sidestepped it by assuming institutional infrastructure.** The open question in [`2026-09-02_state_of_the_project_diagnosis_and_distribution.md`](2026-09-02_state_of_the_project_diagnosis_and_distribution.md) stays open, and it is not open because of a lack of effort on Decifra's part.

### 4.4 A composition opportunity, not a competition

AnnotAISE is the gold-standard collection tool Decifra does not have and arguably should not build. Its output is a CSV with one row per annotation, including annotator ID and record identifier — which is the shape Decifra's `human_labels` table wants. Collecting human gold labels in AnnotAISE and feeding them into Decifra's Validation screen is a natural composition, and it would let Decifra stay out of the multi-annotator coordination business entirely.

This is a concrete question to put to the authors at the SBES Tools demonstration session (Sept 11, 11:00, room IME-CEC).

---

## 5. Bottom line

Halterman & Keith (2026) is a substantially stronger paper than Mercês et al. (2026) — tighter claims, better-isolated evidence, more honest about its limits — but it ships no code. Mercês et al. is a competent exploratory study with a genuinely reusable taxonomy and a badly under-specified quantitative apparatus, whose most valuable output for Decifra is a scaling law for LLM over-coding as codebook size grows. AnnotAISE is the most mature *software* of the three by a wide margin and the weakest *evaluation*, because TAM cannot tell you whether the data coming out is any good.

None of the three does what Decifra proposes. Halterman & Keith describe the workflow and decline to build it, and explicitly caution against automating the codebook itself. Mercês et al. hand-roll Decifra's engine for one study and throw it away, recommending guidelines instead of a tool. AnnotAISE builds durable software for the opposite half of the problem, keeping the LLM out of the coding loop and leaving the codebook unstructured.

The gap Decifra occupies is real and, as of CBSoft 2026, still unoccupied. The binding constraint is not the idea — it is that the one group that shipped comparable software required Docker and a server to do it.
