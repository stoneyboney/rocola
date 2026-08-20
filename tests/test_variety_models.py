"""SPEC §6.3, and CLAUDE.md §5's insistence that `general` wins when unsure."""

from __future__ import annotations

import pytest

from rocola_prep.variety.models import (
    Register,
    Variety,
    VarietySense,
    parse_register,
    parse_variety,
)


class TestTheEnums:
    def test_has_the_twenty_one_varieties_spec_6_3_names(self) -> None:
        assert len(Variety) == 21
        assert Variety.GENERAL.value == "general"
        for member in Variety:
            if member is not Variety.GENERAL:
                assert member.value.startswith("es-")

    def test_has_the_six_registers(self) -> None:
        assert {r.value for r in Register} == {
            "neutral",
            "coloquial",
            "vulgar",
            "poetic",
            "arcaic",
            "albur",
        }

    def test_general_is_not_regional(self) -> None:
        assert not Variety.GENERAL.is_regional
        assert Variety.MX.is_regional

    def test_the_badge_is_the_bare_code(self) -> None:
        # SPEC §9.2 renders "🇦🇷 AR · coloquial".
        assert Variety.AR.badge == "AR"
        assert Variety.MX.badge == "MX"
        assert Variety.GENERAL.badge == ""


class TestGeneralWins:
    """CLAUDE.md §5: over-tagging is the expected failure mode."""

    @pytest.mark.parametrize(
        "value",
        [
            None,
            "",
            "   ",
            "general",
            "GENERAL",
            "es-419",  # a real BCP-47 tag, not one §6.3 lists
            "mexican",
            "Mexico",
            "latin american",
            42,
            [],
            {"variety": "es-MX"},
        ],
    )
    def test_anything_unrecognised_becomes_general(self, value: object) -> None:
        # Never an exception: a model that invents a code should produce an
        # untagged sense, not a failed batch and a wasted retry.
        assert parse_variety(value) is Variety.GENERAL

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("es-MX", Variety.MX),
            ("es_mx", Variety.MX),
            ("ES-MX", Variety.MX),
            ("mx", Variety.MX),
            ("MX", Variety.MX),
            ("  es-AR  ", Variety.AR),
            (Variety.CU, Variety.CU),
        ],
    )
    def test_accepts_the_shapes_a_model_actually_answers_in(
        self, value: object, expected: Variety
    ) -> None:
        assert parse_variety(value) is expected

    @pytest.mark.parametrize(
        "value", [None, "", "casual", "slang", "informal", 7, "NEUTRAL "]
    )
    def test_an_unrecognised_register_becomes_neutral(self, value: object) -> None:
        assert parse_register(value) is Register.NEUTRAL

    def test_register_parses_what_the_schema_offers(self) -> None:
        assert parse_register("coloquial") is Register.COLOQUIAL
        assert parse_register("ALBUR") is Register.ALBUR

    def test_the_asymmetry_is_the_point(self) -> None:
        # A word wrongly `general` is a badge nobody sees. A word wrongly
        # `es-AR` is a badge that lies, rendered next to "MX: …" as fact.
        # So every uncertain path lands on the first kind.
        for junk in ["es-999", "unknown", "?", "n/a"]:
            assert parse_variety(junk) is Variety.GENERAL


class TestTheBadgeRule:
    """SPEC §9.2's table."""

    HOME = Variety.MX

    def sense(self, variety: Variety) -> VarietySense:
        return VarietySense(lemma="x", pos="NOUN", variety=variety)

    def test_general_gets_no_badge(self) -> None:
        assert not self.sense(Variety.GENERAL).needs_badge(self.HOME)

    def test_the_home_dialect_gets_no_badge(self) -> None:
        # In Monterrey a Monterrey word is just a word.
        assert not self.sense(Variety.MX).needs_badge(self.HOME)

    def test_any_other_variety_gets_one(self) -> None:
        for variety in [Variety.AR, Variety.ES, Variety.CU, Variety.PR]:
            assert self.sense(variety).needs_badge(self.HOME)

    def test_the_home_dialect_is_not_hard_coded(self) -> None:
        # CLAUDE.md §5: `homeDialect` governs all regional rendering and is
        # never hard-coded. Move home to Buenos Aires and MX gains the badge.
        assert self.sense(Variety.MX).needs_badge(Variety.AR)
        assert not self.sense(Variety.AR).needs_badge(Variety.AR)


class TestNormalisation:
    """§6.3's invariants, enforced rather than requested."""

    def test_a_general_sense_cannot_keep_a_home_equivalent(self) -> None:
        # CLAUDE.md §5: never populate it with a synonym for its own sake.
        # The model ignoring that instruction is the expected case.
        sense = VarietySense(
            lemma="corazón",
            pos="NOUN",
            variety=Variety.GENERAL,
            home_equivalent="chavo",
            home_equivalent_note="algo",
        ).normalised(Variety.MX)
        assert sense.home_equivalent is None
        assert sense.home_equivalent_note is None

    def test_a_home_dialect_sense_cannot_either(self) -> None:
        # There is no "what would you say instead" when it is already yours.
        sense = VarietySense(
            lemma="chavo", pos="NOUN", variety=Variety.MX, home_equivalent="morro"
        ).normalised(Variety.MX)
        assert sense.home_equivalent is None

    def test_a_foreign_sense_keeps_it(self) -> None:
        sense = VarietySense(
            lemma="pibe",
            pos="NOUN",
            variety=Variety.AR,
            home_equivalent="chavo",
            home_equivalent_note="In Mexiko sagt man 'chavo'.",
        ).normalised(Variety.MX)
        assert sense.home_equivalent == "chavo"
        assert sense.home_equivalent_note is not None

    def test_normalisation_preserves_everything_else(self) -> None:
        original = VarietySense(
            lemma="pibe",
            pos="NOUN",
            de="Junge",
            en="kid",
            variety=Variety.GENERAL,
            register=Register.COLOQUIAL,
            home_equivalent="chavo",
            morph_note="voseo",
            confidence=0.9,
        )
        sense = original.normalised(Variety.MX)
        assert (sense.de, sense.en) == ("Junge", "kid")
        assert sense.register is Register.COLOQUIAL
        assert sense.morph_note == "voseo"
        assert sense.confidence == 0.9

    def test_morph_note_survives_on_a_general_sense(self) -> None:
        # §9.3's voseo forms are recognition-only regardless of variety, so the
        # note is not swept up with the home equivalent.
        sense = VarietySense(
            lemma="ser", pos="VERB", variety=Variety.GENERAL, morph_note="sos = eres"
        ).normalised(Variety.MX)
        assert sense.morph_note == "sos = eres"


class TestDefaults:
    def test_a_bare_sense_is_general_and_neutral(self) -> None:
        sense = VarietySense(lemma="casa", pos="NOUN")
        assert sense.variety is Variety.GENERAL
        assert sense.register is Register.NEUTRAL
        assert sense.home_equivalent is None
        assert sense.confidence is None

    def test_identity_matches_the_glosstask_shape(self) -> None:
        # So it can key the same dicts molcajete_prep's provider returns.
        assert VarietySense(lemma="casa", pos="NOUN").identity == ("casa", "NOUN")

    def test_is_frozen(self) -> None:
        sense = VarietySense(lemma="casa", pos="NOUN")
        with pytest.raises(Exception):
            sense.variety = Variety.MX  # type: ignore[misc]
