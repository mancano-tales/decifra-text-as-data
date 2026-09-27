from __future__ import annotations

from typing import Literal

import ftfy
from pydantic import BaseModel, Field, create_model

VERBAL_PROBABILITY_LABELS = [
    "quase_certa",
    "muito_provavel",
    "provavel",
    "cinquenta_e_cinquenta",
    "improvavel",
    "muito_improvavel",
    "quase_impossivel",
]

VERBAL_PROBABILITY_DEFINITIONS = {
    "quase_certa": "Quase certamente observaríamos esta evidência se a hipótese fosse verdadeira (~0.95).",
    "muito_provavel": "Muito provavelmente observaríamos esta evidência (~0.80).",
    "provavel": "Provavelmente observaríamos esta evidência (~0.65).",
    "cinquenta_e_cinquenta": "Poderia ou não ocorrer — a evidência não discrimina entre as hipóteses (~0.50).",
    "improvavel": "Improvável, mas possível, observar esta evidência (~0.35).",
    "muito_improvavel": "Muito improvável observar esta evidência se a hipótese fosse verdadeira (~0.20).",
    "quase_impossivel": "Quase impossível observar esta evidência sob esta hipótese — hoop test (~0.05).",
}


def fix_mojibake(text: str) -> str:
    """Repair text corrupted by a wrong-codec round-trip during the original
    Folha scrape (e.g. `institui\\xe7\\xf5es` instead of `instituições`)."""
    return ftfy.fix_text(text)


def build_hypothesis_lookup(tb1_rows: list[dict]) -> dict[str, tuple[str, str]]:
    """Group tb1_hypotheses rows by `hypothesis_group_id` and return
    {pair_code: (side_a_name, side_b_name)} keyed by the pair code as it
    appears in the sheet (e.g. "H1"), sorted by pk_hyp__code so side 'a'
    always comes first. Only pairs with exactly two rows are included."""
    by_group: dict[str, list[dict]] = {}
    for row in tb1_rows:
        # hypothesis_group_id is already the pair code (e.g. "H1") in the
        # real workbook, not a bare number -- str() is just cheap safety
        # against a stray non-string cell, not a coercion of numeric data.
        by_group.setdefault(str(row["hypothesis_group_id"]), []).append(row)

    lookup: dict[str, tuple[str, str]] = {}
    for pair_code, rows in by_group.items():
        if len(rows) != 2:
            continue
        rows = sorted(rows, key=lambda r: r["pk_hyp__code"])
        lookup[pair_code] = (rows[0]["hypothesis_name"], rows[1]["hypothesis_name"])
    return lookup


HYPOTHESIS_DEFINITIONS: dict[str, dict] = {
    "H1": {
        "primary_question": "How was access to tertiary education redistributed?",
        "secondary_question": "What is the redistributive mechanism -- expansion or de-commodification?",
        "a": {
            "name": "Conditional Partisan Expansion",
            "mechanism": (
                "In elite-stage systems right-wing parties drive enrollment expansion because the "
                "marginal beneficiaries are their own (relatively advantaged) constituents; "
                "left-wing parties prefer expansion only after massification reverses the income "
                "profile of new entrants. Expansion magnitude and timing track partisan turnover "
                "and the elite-to-mass threshold."
            ),
            "premises": (
                "Gross enrollment expansion is itself the redistributive lever, and its "
                "timing/magnitude co-vary with the governing party's position and the elite/mass "
                "stage; the income composition of entrants shifts as a by-product of expansion "
                "volume."
            ),
        },
        "b": {
            "name": "De-commodification as Redistributive Mechanism",
            "mechanism": (
                "Gross enrollment expansion is a weak proxy for redistribution; the redistributive "
                "cleavage runs through the de-commodification of access -- means-tested subsidies "
                "(ProUni), affirmative action (quotas), and tuition-fee / student-finance policy. "
                "Expansion without de-commodification does not redistribute."
            ),
            "premises": (
                "The income composition of entrants shifts with the adoption of de-commodifying "
                "instruments rather than with expansion volume; inequality reduction precedes or "
                "exceeds what expansion alone would predict only when de-commodifying policies are "
                "adopted."
            ),
        },
    },
    "H2": {
        "primary_question": "How was access to tertiary education redistributed?",
        "secondary_question": (
            "Which actors determine the redistributive content -- governing parties alone, or "
            "plural non-partisan actors?"
        ),
        "a": {
            "name": "Strict Partisan-Primacy",
            "mechanism": (
                "Party preferences -> policy design -> distributive content. Governing parties are "
                "the decisive proposers and veto-players; social movements and the educational "
                "business sector operate only within the political space parties create, as "
                "followers with no autonomous effect on outputs."
            ),
            "premises": (
                "Governing parties are the central causal agent; non-partisan actors do not change "
                "policy outputs against governmental preference."
            ),
        },
        "b": {
            "name": "Co-production by Plural Non-Partisan Actors",
            "mechanism": (
                "Grassroots movements -- particularly the Black movement and student organisations "
                "-- and for-profit educational conglomerates affect policy with causal autonomy: "
                "they set agendas, veto proposals, and create faits accomplis that constrain "
                "subsequent governments. Outcomes such as the racial design of affirmative action "
                "and the dilution of ProUni/FIES cannot be explained by partisan competition alone."
            ),
            "premises": (
                "Non-partisan actors exert autonomous causal power that shapes outcomes even "
                "against governmental preferences; under organized pressure, partisan actors "
                "supersede their first preferences to reach agreements with non-partisan actors."
            ),
        },
    },
    "H3": {
        "primary_question": "How was access to tertiary education redistributed?",
        "secondary_question": (
            "Why did private provision become dominant -- ideological preference or path-dependent "
            "fiscal constraint?"
        ),
        "a": {
            "name": "Ideological Preference for Private Provision",
            "mechanism": (
                "Right-wing governments (Cardoso/PSDB, Temer, Bolsonaro) are close to market actors "
                "and promote private-sector expansion as an expression of an ideological preference "
                "for market-based provision."
            ),
            "premises": (
                "Private-sector expansion co-varies with party orientation once fiscal constraints "
                "are held constant; right-wing governments use regulatory instruments to facilitate "
                "private HEI entry and growth, while left-wing governments restrict it."
            ),
        },
        "b": {
            "name": "Path Dependence and Fiscal Constraint",
            "mechanism": (
                "Private-sector dominance reflects the institutional architecture inherited from "
                "the 1968 reform (already private-dominant before the 1990s), the rising cost of "
                "reversing legacy public arrangements, and binding fiscal constraints that limit "
                "public expansion irrespective of governing party. Business power -- structural "
                "indispensability, institutional delegation/lock-in, and instrumental lobbying -- "
                "sustains the arrangement."
            ),
            "premises": (
                "Private expansion does not co-vary with party orientation once fiscal constraints "
                "are controlled; public expansion occurs at the margin of fiscal adjustment "
                "regardless of which party governs."
            ),
        },
    },
}

PROBABILITY_BOUNDARY_NOTES: dict[str, str] = {
    "quase_certa": (
        "Reserve for evidence that would be genuinely surprising or hard to explain if the rival "
        "hypothesis were true instead -- not just evidence that fits this hypothesis's general "
        "topic."
    ),
    "muito_provavel": (
        "Use when the evidence clearly favors this hypothesis's specific mechanism over the "
        "rival's, even if not as decisively as quase_certa."
    ),
    "provavel": (
        "Use when the evidence leans toward this hypothesis but could still be loosely "
        "accommodated by the rival hypothesis too."
    ),
    "cinquenta_e_cinquenta": (
        "The correct answer whenever the evidence is topically relevant but would be roughly "
        "equally expected under either hypothesis in this pair -- topical relevance is not the "
        "same as discriminating power. Most evidence that only confirms the general subject area, "
        "without speaking to which specific mechanism actually operated, belongs here."
    ),
    "improvavel": (
        "Use when the evidence leans against this hypothesis, favoring the rival's mechanism "
        "instead, though not decisively."
    ),
    "muito_improvavel": (
        "Use when the evidence clearly favors the rival hypothesis's specific mechanism over this "
        "one."
    ),
    "quase_impossivel": (
        "A hoop test failure: evidence that is very hard to reconcile with this hypothesis even "
        "generously interpreted -- e.g. evidence that directly contradicts a premise this "
        "hypothesis states."
    ),
}


def build_enriched_hypothesis_codebook_spec(pair_code: str, side_label: str) -> dict:
    """Build a codebook spec for one side of a V7 hypothesis pair, with the
    full theoretical definition (mechanism + premises, not just the short
    hypothesis name) and explicit scope-check / discriminating-power /
    consistency instructions in `description`, plus per-category
    `boundary_notes`.

    This exists because the bare-bones codebook this pilot originally used
    (name-only description, no boundary_notes) produced exactly the
    failure modes an under-specified codebook predicts when run for real
    (2026-09-01, `agy`/Gemini): a hypothesis's own scope condition ignored
    outright (H3a specifically names right-wing/market-aligned governments;
    scored `muito_provavel` anyway for a left-wing government's policy),
    both sides of a pair scored `muito_provavel` in over a third of cases
    (near-zero discriminating power), and inconsistent treatment of
    near-identical evidence. The fix is a richer prompt, not a different
    model -- see "Why the validation step is not optional" in
    `docs/PRODUCT_BRIEF.md`, and this project's memory note on diagnosing
    prompt/codebook gaps before model choice."""
    pair = HYPOTHESIS_DEFINITIONS[pair_code]
    other_label = "b" if side_label == "a" else "a"
    this_side = pair[side_label]
    other_side = pair[other_label]

    description = (
        f"Inhabit the world of the hypothesis '{this_side['name']}' and ask: if this hypothesis "
        "were true, how expected would this evidence be? (Fairfield & Charman 2022, Bayesian "
        "process tracing.)\n\n"
        f"Research question: {pair['primary_question']}\n"
        f"This pair asks: {pair['secondary_question']}\n\n"
        f"THE HYPOTHESIS YOU ARE EVALUATING -- {this_side['name']}:\n"
        f"Mechanism: {this_side['mechanism']}\n"
        f"Premises: {this_side['premises']}\n\n"
        f"THE RIVAL HYPOTHESIS in this pair -- {other_side['name']} (do not evaluate this one; "
        "use it only as the counterfactual comparison):\n"
        f"Mechanism: {other_side['mechanism']}\n\n"
        "Critical instructions:\n"
        "1. Scope check: before scoring, verify the evidence actually concerns the specific "
        "actor/party/mechanism type this hypothesis names. Do not score high just because the "
        "topic is generally related to the research question -- check whether the evidence's "
        "actual actor (e.g. which party governs in the evidence) matches what this specific "
        "hypothesis requires.\n"
        "2. Discriminating power: your score must reflect how much MORE expected this evidence "
        "is under THIS hypothesis than under the rival hypothesis above -- not merely whether it "
        "is topically consistent with this hypothesis. Ask explicitly: would a reasonable "
        "observer expect this same evidence about equally well under the rival hypothesis? If "
        "yes, score 'cinquenta_e_cinquenta' regardless of how relevant the evidence looks.\n"
        "3. Consistency: if evidence shows a policy being tightened, loosened, or reversed, "
        "state which direction of change this hypothesis's own mechanism predicts before "
        "scoring, and apply that same rule to any similarly-structured evidence -- do not flip "
        "the interpretation between similar evidence without a reason tied to the hypothesis's "
        "own stated mechanism."
    )

    categories = [
        {
            "label": label,
            "definition": VERBAL_PROBABILITY_DEFINITIONS[label],
            "boundary_notes": PROBABILITY_BOUNDARY_NOTES[label],
        }
        for label in VERBAL_PROBABILITY_LABELS
    ]

    return {
        "concept": f"{pair_code}_{side_label}_probability",
        "description": description,
        "categories": categories,
    }


def build_joint_hypothesis_messages_and_schema(
    pair_code: str, evidence_text: str
) -> tuple[list[dict], type[BaseModel]]:
    """Build a single-call prompt that scores BOTH sides of a hypothesis
    pair against one evidence text at once, instead of the two separate,
    blind calls `build_enriched_hypothesis_codebook_spec` produces.

    Experimental (V7 pipeline tuning item 3, see
    docs/research/2026-09-02_llm_pipeline_verification_methodology.md's
    "structural limitation" section): the two-blind-calls design means
    side A's call never sees side A's own answer for side B, so nothing
    forces a direct comparison between them -- this is what let both
    sides of a pair score `muito_provavel` in the pre-enrichment pilot,
    near-zero discriminating power. A joint call can't fix a bad
    codebook, but it tests whether forced side-by-side comparison changes
    the answer even with the *same* enriched instructions.

    Deliberately NOT built on the general `Codebook` class: that class is
    architected around exactly one `category` field per call, and a
    joint two-hypothesis judgment fundamentally needs two -- forcing it
    through `Codebook` would mean changing the general engine to support
    one V7-specific experiment, which is exactly what AGENTS.md's
    "keep codebook separate from extraction" rule warns against. This
    stays self-contained in pilot_v7.py instead, calling `CliProvider`
    directly with a hand-built schema."""
    pair = HYPOTHESIS_DEFINITIONS[pair_code]
    side_a, side_b = pair["a"], pair["b"]

    boundary_notes_block = "\n".join(
        f"- {label}: {VERBAL_PROBABILITY_DEFINITIONS[label]} {PROBABILITY_BOUNDARY_NOTES[label]}"
        for label in VERBAL_PROBABILITY_LABELS
    )

    instructions = (
        "You will evaluate ONE piece of evidence against BOTH sides of a competing hypothesis "
        "pair at once, from Bayesian process tracing (Fairfield & Charman 2022). For EACH "
        "hypothesis, ask: if this hypothesis were true, how expected would this evidence be?\n\n"
        f"Research question: {pair['primary_question']}\n"
        f"This pair asks: {pair['secondary_question']}\n\n"
        f"HYPOTHESIS A -- {side_a['name']}:\n"
        f"Mechanism: {side_a['mechanism']}\n"
        f"Premises: {side_a['premises']}\n\n"
        f"HYPOTHESIS B -- {side_b['name']}:\n"
        f"Mechanism: {side_b['mechanism']}\n"
        f"Premises: {side_b['premises']}\n\n"
        "Critical instructions:\n"
        "1. Scope check: for EACH hypothesis, verify the evidence actually concerns the "
        "specific actor/mechanism/party type that hypothesis names -- do not score high just "
        "because the topic is generally related to the research question.\n"
        "2. Discriminating power, scored jointly: score each hypothesis on how much MORE "
        "expected this evidence is under THAT hypothesis than under the other one above. "
        "Because you are seeing both at once, a score on one side should be informed by how "
        "well the SAME evidence fits the other side -- if the evidence is roughly equally "
        "expected under both, BOTH should score 'cinquenta_e_cinquenta'; do not let one "
        "hypothesis's plausibility inflate the other's score by mere association with the same "
        "topic.\n"
        "3. Consistency: if evidence shows a policy being tightened, loosened, or reversed, "
        "state which direction of change each hypothesis's own mechanism predicts before "
        "scoring.\n\n"
        "Category definitions and boundary notes (apply to both categoria_a and categoria_b):\n"
        f"{boundary_notes_block}"
    )

    labels = tuple(VERBAL_PROBABILITY_LABELS)
    schema = create_model(
        "JointHypothesisExtraction",
        categoria_a=(Literal[labels], Field(description=f"Probability score for hypothesis A ({side_a['name']}).")),
        justificativa_a=(str, Field(description="Free-text rationale for categoria_a.")),
        trecho_evidencia_a=(str, Field(description="Verbatim quote grounding categoria_a.")),
        categoria_b=(Literal[labels], Field(description=f"Probability score for hypothesis B ({side_b['name']}).")),
        justificativa_b=(str, Field(description="Free-text rationale for categoria_b.")),
        trecho_evidencia_b=(str, Field(description="Verbatim quote grounding categoria_b.")),
    )
    # Two messages, not one -- lets CliProvider._build_prompt insert its own
    # instructions/evidence delimiter automatically (finding from tuning
    # item 2), the same way every other codebook's prompt gets it, instead
    # of duplicating that formatting decision here.
    messages = [
        {"role": "system", "content": instructions},
        {"role": "user", "content": evidence_text},
    ]
    return messages, schema


def select_gold_rows(
    tb4_rows: list[dict], hypothesis_lookup: dict[str, tuple[str, str]]
) -> tuple[list[dict], list[dict]]:
    """Split tb4_evidence_analisys rows into (kept, skipped).

    Kept: both prob_e_dado_h1 and prob_e_dado_h2 are filled, AND
    fk_hypothesis_group resolves to a real pair definition in
    hypothesis_lookup (built from tb1_hypotheses). Skipped: everything
    else — most commonly, rows tagged with an old free-text group label
    (e.g. "H_nao_partidaria") that isn't a resolvable pair code."""
    kept, skipped = [], []
    for row in tb4_rows:
        has_both_probs = bool(row.get("prob_e_dado_h1")) and bool(row.get("prob_e_dado_h2"))
        resolvable = row.get("fk_hypothesis_group") in hypothesis_lookup
        (kept if has_both_probs and resolvable else skipped).append(row)
    return kept, skipped
