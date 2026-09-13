from text_as_data.codebook import Codebook
from text_as_data.pilot_v7 import (
    VERBAL_PROBABILITY_LABELS,
    build_enriched_hypothesis_codebook_spec,
    build_hypothesis_lookup,
    build_joint_hypothesis_messages_and_schema,
    fix_mojibake,
    select_gold_rows,
)


def test_fix_mojibake_repairs_corrupted_portuguese_text():
    # Real corruption pattern from the V7 workbook: UTF-8 bytes misread as
    # Latin-1 during the original Folha scrape — a lossless round-trip, so
    # the original text is fully recoverable.
    original = "instituições públicas"
    corrupted = original.encode("utf-8").decode("latin-1")
    assert fix_mojibake(corrupted) == original


def test_build_hypothesis_lookup_from_tb1_rows():
    # hypothesis_group_id is already the pair code in the real workbook
    # (e.g. "H1"), not a bare number -- confirmed by direct inspection of
    # the actual tb1_hypotheses sheet.
    tb1_rows = [
        {
            "pk_hyp__code": "H1a",
            "hypothesis_name": "Conditional Partisan Expansion",
            "hypothesis_group_id": "H1",
        },
        {
            "pk_hyp__code": "H1b",
            "hypothesis_name": "De-commodification as Redistributive Mechanism",
            "hypothesis_group_id": "H1",
        },
        {
            "pk_hyp__code": "H3a",
            "hypothesis_name": "Ideological Preference for Private Provision",
            "hypothesis_group_id": "H3",
        },
        {
            "pk_hyp__code": "H3b",
            "hypothesis_name": "Path Dependence and Fiscal Constraint",
            "hypothesis_group_id": "H3",
        },
    ]

    lookup = build_hypothesis_lookup(tb1_rows)

    assert lookup["H1"] == ("Conditional Partisan Expansion", "De-commodification as Redistributive Mechanism")
    assert lookup["H3"] == ("Ideological Preference for Private Provision", "Path Dependence and Fiscal Constraint")
    assert "H_nao_partidaria" not in lookup


def test_build_hypothesis_lookup_with_string_group_ids_matching_real_workbook():
    tb1_rows = [
        {"pk_hyp__code": "H1a", "hypothesis_name": "Side A", "hypothesis_group_id": "H1"},
        {"pk_hyp__code": "H1b", "hypothesis_name": "Side B", "hypothesis_group_id": "H1"},
    ]

    lookup = build_hypothesis_lookup(tb1_rows)

    assert lookup == {"H1": ("Side A", "Side B")}


def test_select_gold_rows_keeps_only_resolvable_pairs_with_both_probs():
    tb4_rows = [
        {"fk_id_ev": "ev1", "fk_hypothesis_group": "H1", "prob_e_dado_h1": "provavel", "prob_e_dado_h2": "improvavel"},
        {"fk_id_ev": "ev2", "fk_hypothesis_group": "H_nao_partidaria", "prob_e_dado_h1": "provavel", "prob_e_dado_h2": "provavel"},
        {"fk_id_ev": "ev3", "fk_hypothesis_group": "H3", "prob_e_dado_h1": None, "prob_e_dado_h2": "provavel"},
        {"fk_id_ev": "ev4", "fk_hypothesis_group": "H3", "prob_e_dado_h1": "quase_certa", "prob_e_dado_h2": "quase_impossivel"},
    ]
    lookup = {"H1": ("A", "B"), "H3": ("C", "D")}

    kept, skipped = select_gold_rows(tb4_rows, lookup)

    assert [r["fk_id_ev"] for r in kept] == ["ev1", "ev4"]
    assert [r["fk_id_ev"] for r in skipped] == ["ev2", "ev3"]


def test_verbal_probability_labels_has_seven_levels_in_scale_order():
    assert VERBAL_PROBABILITY_LABELS == [
        "quase_certa",
        "muito_provavel",
        "provavel",
        "cinquenta_e_cinquenta",
        "improvavel",
        "muito_improvavel",
        "quase_impossivel",
    ]


def test_enriched_codebook_spec_embeds_full_mechanism_not_just_hypothesis_name():
    # The bare-bones codebook this pilot originally used only named the
    # hypothesis ("Ideological Preference for Private Provision") without
    # its actual scope condition (specifically right-wing/market-aligned
    # governments) -- and a real run against this exact hypothesis scored
    # a left-wing government's policy as muito_provavel anyway. The
    # mechanism text is what states that scope condition, so it must
    # actually be in the description the model sees, not just the name.
    spec = build_enriched_hypothesis_codebook_spec("H3", "a")

    assert "Ideological Preference for Private Provision" in spec["description"]
    assert "Right-wing governments" in spec["description"]
    assert "Path Dependence and Fiscal Constraint" in spec["description"]  # the rival, for contrast


def test_enriched_codebook_spec_instructs_discriminating_power_and_scope_check():
    spec = build_enriched_hypothesis_codebook_spec("H1", "b")

    assert "Scope check" in spec["description"]
    assert "Discriminating power" in spec["description"]
    assert "Consistency" in spec["description"]


def test_enriched_codebook_spec_gives_every_category_boundary_notes():
    spec = build_enriched_hypothesis_codebook_spec("H2", "a")

    for category in spec["categories"]:
        assert category["boundary_notes"], f"category {category['label']!r} has no boundary_notes"


def test_enriched_codebook_spec_is_a_valid_codebook():
    # Round-trips through the real Codebook loader used by run_extraction --
    # this is the actual contract the enriched spec must honor, not just a
    # dict shape check.
    spec = build_enriched_hypothesis_codebook_spec("H1", "a")

    codebook = Codebook._from_spec(spec)

    assert set(codebook.schema.model_fields["category"].annotation.__args__) == set(VERBAL_PROBABILITY_LABELS)
    assert "Scope check" in codebook.instructions
    assert "Boundary notes:" in codebook.instructions


def test_enriched_codebook_spec_covers_both_sides_of_all_three_pairs():
    for pair_code in ("H1", "H2", "H3"):
        for side_label in ("a", "b"):
            spec = build_enriched_hypothesis_codebook_spec(pair_code, side_label)
            assert spec["concept"] == f"{pair_code}_{side_label}_probability"
            assert len(spec["categories"]) == len(VERBAL_PROBABILITY_LABELS)


def test_joint_hypothesis_messages_include_both_sides_and_the_evidence():
    messages, schema = build_joint_hypothesis_messages_and_schema("H1", "some evidence text")

    assert messages[0]["role"] == "system"
    assert "Conditional Partisan Expansion" in messages[0]["content"]
    assert "De-commodification as Redistributive Mechanism" in messages[0]["content"]
    assert messages[-1] == {"role": "user", "content": "some evidence text"}


def test_joint_hypothesis_schema_has_independent_fields_for_both_sides():
    _, schema = build_joint_hypothesis_messages_and_schema("H2", "x")

    fields = schema.model_fields
    assert set(fields) == {
        "categoria_a", "justificativa_a", "trecho_evidencia_a",
        "categoria_b", "justificativa_b", "trecho_evidencia_b",
    }
    assert set(fields["categoria_a"].annotation.__args__) == set(VERBAL_PROBABILITY_LABELS)
    assert set(fields["categoria_b"].annotation.__args__) == set(VERBAL_PROBABILITY_LABELS)


def test_joint_hypothesis_messages_differ_by_pair_code():
    messages_h1, _ = build_joint_hypothesis_messages_and_schema("H1", "x")
    messages_h3, _ = build_joint_hypothesis_messages_and_schema("H3", "x")

    assert messages_h1[0]["content"] != messages_h3[0]["content"]
    assert "Ideological Preference for Private Provision" in messages_h3[0]["content"]
