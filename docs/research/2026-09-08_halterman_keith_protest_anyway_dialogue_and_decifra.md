# Dialogue with Halterman & Keith (2026): "What is a protest anyway?" and Decifra (`cifra-text-as-data`)

*Date: September 8, 2026*
*Analyzed paper:* Andrew Halterman & Katherine A. Keith, "What is a protest anyway? Codebook conceptualization is still a first-order concern in LLM-era classification," *Proceedings of the 64th Annual Meeting of the Association for Computational Linguistics* (Volume 1: Long Papers), pages 2043–2059, ACL 2026.
*Source:* PDF supplied by the author (`G:\My Drive\[[1]] Kami Uploads\Halterman and Keith - 2025 - What is a protest anyway...pdf`), read directly via `pypdf` (the file carries owner-level copy restrictions that block naive PDF text extraction, but no user password).
*Target application:* Decifra (`cifra-text-as-data`)

**A note on how this document was produced.** The source PDF is a copyrighted, published ACL paper. This document is an original summary and analysis in my own words, not a transcript — no full-text copy of the paper was committed to this (public) repository. Short quotations are attributed and kept under ACL's normal fair-use scope for a handful of load-bearing phrases. If a full local copy of the PDF would be useful for the team's own reference, it should live outside version control (e.g. a personal `docs/research/papers/` added to `.gitignore`), not in a public GitHub repo — happy to wire that up on request, but I did not do it unprompted.

This is the second Halterman & Keith paper this project engages with; the first (`Codebook LLMs`, 2025) already has a dialogue at [`2026-09-01_halterman_keith_codebook_llms_dialogue_and_cifra.md`](2026-09-01_halterman_keith_codebook_llms_dialogue_and_cifra.md). This paper is a conceptual/theoretical follow-up, not an empirical benchmark — it has no new dataset or model results, only a worked example, four real-world codebook comparisons, and a simulation.

---

## 1. What the paper actually argues

The paper's thesis, stated plainly in its own words: **"conceptualization remains a first-order concern, even in the LLM-era."** It defends this with three claims:

- **Claim 1 — annotation error decomposes into two independent failure modes.** *Conceptualization error* comes from an incomplete codebook (the definition itself doesn't resolve some real case). *Scoring error* comes from an annotator — human or LLM — misapplying a codebook that is otherwise fine. These are orthogonal: a perfect annotator can still produce a wrong label if the codebook never told them what to do with, say, a violent labor strike.
- **Claim 2 — LLMs remove the forcing function that used to guarantee conceptualization happened at all.** Human annotators ask clarifying questions ("do labor strikes count?") when a codebook is vague, which historically forced analysts to write precise definitions before any coding could start. An LLM never asks; it "fails silently," generating a plausible-looking label for an underspecified concept instead of flagging the gap. The paper cites real papers (Brandt et al. 2024, Ziems et al. 2024) that ran LLM classification with nothing but a bare label name as the "codebook."
- **Claim 3 — the sharpest and most useful claim for Decifra: conceptualization-induced bias cannot be fixed downstream.** Neither a more accurate LLM nor post-hoc statistical bias correction (PPI, DSL — see below) can repair the damage from an incomplete codebook. Their simulation (§5, Figure 3) is direct: under a *complete* codebook, correction methods recover the true effect regardless of LLM error rate, with variance shrinking as the LLM gets more accurate. Under an *incomplete* codebook (one that doesn't say whether violent events count as protests), the corrected estimate is **biased at every LLM error rate, including zero** — because the human "gold standard" annotators, applying the same incomplete codebook, are themselves systematically wrong relative to the researcher's actual construct.

That last point is the one worth sitting with: **two annotators (or an LLM and a human) can agree with each other completely and still both be wrong**, if they're agreeing on the wrong question. Agreement measures scoring consistency, not conceptual completeness.

### 1.1 Definition specificity: three types

The paper (building on Adcock & Collier 2001) sorts codebook definitions into three levels:

- **Type I — surface form only**: `"Is this a protest?"` No definition at all; relies on the LLM's pretrained sense of the word.
- **Type II — dictionary entry**: a generic, context-free definition ("a public manifestation of dissent").
- **Type III — stipulative definition**: a definition custom-written for the specific research question, with explicit inclusion/exclusion criteria. Example given (ACLED's actual definition): *"an in-person public demonstration of three or more participants in which the participants do not engage in violence, though violence may be used against them."*

Their claim: most real social-science use cases need Type III, and LLMs are exactly what tempts analysts to settle for Type I.

### 1.2 What makes a codebook "complete"

Two proposed (and explicitly imperfect) standards:
1. **Community consensus** — a codebook is complete if domain experts agree it addresses every aspect they consider relevant to class membership.
2. **Expert-agreement as an operational test** — two experts, coding independently from the codebook alone with no side communication, should reach near-perfect agreement (construct reliability).

Figure 2 of the paper operationalizes standard 1 concretely: it compares four real, in-production PROTEST codebooks (ACE, ACLED, CAMEO, the Crowd Counting Consortium) across nine dimensions — does the definition include or exclude civil disobedience, hunger strikes, labor strikes, online protests, protests against a business, protests in favor of a policy, violence *against* protesters, violence *by* protesters, and single-person protests. All four codebooks disagree with each other on multiple dimensions. None is "more correct" — they encode different research questions.

### 1.3 The practical recommendation: the "pragmatist" workflow

The paper frames three archetypes and recommends the middle one:
- **Pessimist**: hand-code a small sample only. Unbiased, but slow, expensive, high-variance (small *n*).
- **Optimist**: LLM-label everything with a bare label as the "codebook." Cheap, but biased — from both scoring error and conceptualization error.
- **Pragmatist (recommended)**: write a real (Type III) codebook, LLM-label the full corpus, hand-code a small gold subset, then combine the two via a **post-hoc bias-correction estimator** — Prediction-Powered Inference (PPI; Angelopoulos et al. 2023) for a simple prevalence/proportion estimate, or Design-based Supervised Learning (DSL; Egami et al. 2023) for regression coefficients. The paper spells out PPI concretely as **Algorithm 1**: the LLM-only estimate on all *N* documents, minus an empirical "rectifier" (the LLM's own mean error rate measured on the *n* gold-labeled documents), with a variance estimate combining both samples for a valid 95% CI.

That's it as a re-derivable estimator, not just a citation — the paper gives closed-form update rules a tool could implement directly.

---

## 2. How this maps onto Decifra, concretely

I checked this against Decifra's actual code rather than just the architecture description in `AGENTS.md`, so the gaps below are grounded in what [`codebook.py`](../../src/text_as_data/codebook.py) and [`validation.py`](../../src/text_as_data/validation.py) do today, not assumptions.

### 2.1 Where Decifra already matches the paper's recommendation

- **The codebook schema is already Type III by construction.** `label` + `definition` + `positive_examples` + `negative_examples` + `boundary_notes` (`validate_spec()` in `codebook.py`) is not a generic dictionary entry — `boundary_notes` in particular exists specifically to force the "does a labor strike count?" question the paper says LLMs let analysts skip. This is a real, non-coincidental alignment: `AGENTS.md`'s codebook format was explicitly modeled on the *first* Halterman & Keith paper's Stage 0. Good news — this second paper doesn't ask for a schema change.
- **`agreement_report()` already computes exactly the scoring-error diagnostics the paper's Claim 1 calls for**: accuracy, Cohen's kappa (chance-corrected, so it won't be fooled by a majority-class LLM), per-category precision/recall/F1, and a full disagreement list for manual reading. This is real infrastructure for catching scoring error.

### 2.2 The real gap: Decifra currently has no way to catch — or even name — conceptualization error

This is the paper's sharpest point, and it's a gap, not a refinement. `agreement_report()` measures whether the LLM's labels match a human gold set. If both the LLM *and* the human gold-coder are working from the same underspecified codebook (say, `boundary_notes` never addresses violent protests), they can score a perfect Cohen's kappa of 1.0 on that dimension and Decifra's Validation screen will report it as a clean bill of health — while the underlying research conclusion is still biased, per Claim 3's own simulation. Kappa is a scoring-error instrument; it is structurally blind to conceptualization error by the paper's own definition, because conceptualization error is defined as something an *ideal* annotator would also get "wrong" relative to the researcher's true construct.

Concretely, `AGENTS.md`'s existing "Why validation is not optional" section already gestures at this ("off-the-shelf LLMs frequently ignore a codebook's specific operationalization"), but that framing is about the *first* paper's finding (LLMs deviating from a codebook that's otherwise fine). This second paper's finding is stronger and different: **even if the LLM followed the codebook perfectly, the codebook itself can still be silently wrong**, and no amount of LLM accuracy or statistical correction fixes that. `AGENTS.md` doesn't currently make this distinction, and the Validation screen's UI has no mechanism to warn about it (a high kappa currently reads as unambiguously good news).

### 2.3 Decifra has no bias-corrected downstream estimate — only a diagnostic

`agreement_report()` tells a researcher "here's how often the LLM and your gold coder agree." It does not give them "here's your corrected estimate of the prevalence of `protest` in your full corpus, with a valid 95% CI" — which is the actual thing the paper's "pragmatist" workflow is built to produce, and the reason a researcher would run this pipeline in the first place. The paper's Algorithm 1 (PPI) is a small, well-specified, already-proven-unbiased estimator that takes exactly the two things Decifra already has after a run — full-corpus LLM predictions and a gold subset — and produces exactly the thing `agreement_report()` currently doesn't: a usable number for a paper, not just a QA metric.

### 2.4 A narrower but concrete data-integrity risk: mismatched codebook versions

The paper's Appendix Table A1 names a failure mode it calls "procedural error": the LLM gets the complete codebook `C`, but the human annotators (or an earlier hand-coded gold set) were actually coded against an earlier or different version `C'` of the same codebook. Decifra's `human_labels` table currently has no explicit link back to a specific codebook *version* — if a user iterates on a codebook (a normal, expected workflow per `AGENTS.md`) and re-runs validation against an older gold set, nothing currently checks or warns that the two were coded against different codebook text. This is a plausible, silent way to get exactly the biased-but-invisible outcome Claim 3 warns about.

---

## 3. Concrete, prioritized recommendations

Roughly in order of value-for-effort — none of this is implemented yet; these are proposals for the next planning pass, not changes made in this session.

1. **Implement a PPI-corrected prevalence estimate as a Validation screen output.** Add a small function alongside `agreement_report()` (e.g. `ppi_prevalence_estimate()`) implementing the paper's Algorithm 1 per category: point estimate, empirical rectifier from the gold subset, and a 95% CI. This is the single highest-value addition — it turns the Validation screen from "a QA dashboard" into something that produces an actual citable number. Low implementation risk: the algorithm is fully specified in closed form in the paper, needs only `numpy`/`pandas`, and Decifra already has both required inputs (full-corpus LLM output, gold subset) at validation time.
2. **Sharpen `AGENTS.md`'s "Why validation is not optional" section and the site's `validation.qmd`** to explicitly distinguish conceptualization error from scoring error, and to state plainly that a high Cohen's kappa does not certify a complete codebook — it only certifies that the LLM and the human gold-coder agree with each other. This is a documentation-only change but a substantive correctness one: it's the single most important idea in this paper and Decifra's current docs don't yet carry it.
3. **Surface that same caveat in the Validation screen's own UI copy** (a tooltip or note next to the kappa score), not just in docs nobody reads before shipping a result. Cheap, and it's exactly the kind of thing that prevents a researcher from mistaking "the LLM agrees with my coder" for "my codebook is right."
4. **Warn on codebook-version mismatch between a run and its gold set** — the Appendix's "procedural error." Requires storing which codebook version (or a hash of the codebook text) a `human_labels` batch was coded against, and flagging a mismatch on the Validation screen if it differs from the run's codebook. Medium effort, but closes a real silent-failure path.
5. **Offer the four real PROTEST codebooks (Figure 2 / Appendix B) as a starter/tutorial codebook**, most naturally ACLED's — it's the shortest (~40 tokens), it's an openly published methodological definition already reused this way across the field, and it doubles as a worked example of what a good `boundary_notes` section (its explicit exclusion list: symbolic acts, legislative walkouts, unaccompanied strikes, individual self-harm) looks like in practice. Would give new Decifra users something better than a blank form on first launch of the Codebook Editor.
6. **Do not build DSL-style regression correction** (the paper's more general estimator, for downstream regression coefficients rather than a simple prevalence). It requires the user to specify a full regression model with covariates inside the tool, which is a much bigger scope increase — closer to "Decifra becomes a stats package" than "Decifra reports a corrected number." Worth a `TODO.md` line as a known future direction, not worth planning now.

None of these require touching `extraction.py` or the codebook YAML format — they're additive to `validation.py`, docs, and the frontend's Validation screen, consistent with `AGENTS.md`'s existing rule to keep the codebook format stable and independent of the engine underneath it.

---

## 4. Bottom line

This paper doesn't ask Decifra to change its architecture — the codebook schema, the dual-provider engine, and the existing agreement metrics all remain sound. What it adds is a missing *category* of risk (conceptualization error, as distinct from scoring error) that the current Validation screen has no way to detect or even name, plus a ready-to-implement estimator (PPI) that would let the tool produce an actual bias-corrected research number instead of only a QA diagnostic. Of the six recommendations above, #1 (PPI) and #2 (sharpening the docs) are the two with the best ratio of scientific value to implementation cost.
