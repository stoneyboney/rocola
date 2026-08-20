"""SPEC §7.5's prompt and parser. Nothing here reaches Ollama."""

from __future__ import annotations

import pytest

from molcajete_prep.glossing.ollama import Rejected
from molcajete_prep.glossing.provider import GlossTask

from rocola_prep.variety.models import Register, Variety
from rocola_prep.variety.prompts import (
    PROMPT_VERSION,
    VARIETY_SCHEMA,
    VarietyParser,
    build_system_prompt,
    render_correction,
)

CORAZON = GlossTask(lemma="corazón", pos="NOUN", example_es="Ay corazón, no llores más")
PIBE = GlossTask(lemma="pibe", pos="NOUN", example_es="El pibe del barrio no vuelve")


def answer(lemma="corazón", pos="NOUN", **overrides) -> dict:
    built = {
        "lemma": lemma,
        "pos": pos,
        "glossDe": "das Herz",
        "glossEn": "heart",
        "variety": "general",
        "register": "neutral",
        "homeEquivalent": None,
        "homeEquivalentNote": None,
        "morphNote": None,
        "notSpanish": False,
        "confidence": 0.98,
    }
    built.update(overrides)
    return built


class TestTheSchema:
    def test_offers_only_the_varieties_spec_6_3_names(self) -> None:
        item = VARIETY_SCHEMA["properties"]["glosses"]["items"]
        allowed = item["properties"]["variety"]["enum"]
        assert len(allowed) == 21
        assert "general" in allowed
        assert "es-MX" in allowed
        assert "es-419" not in allowed

    def test_offers_only_the_six_registers(self) -> None:
        item = VARIETY_SCHEMA["properties"]["glosses"]["items"]
        assert set(item["properties"]["register"]["enum"]) == {
            "neutral", "coloquial", "vulgar", "poetic", "arcaic", "albur"
        }

    def test_german_comes_before_english(self) -> None:
        # §7.5: "Require glossDe first — the model produces better German when
        # it is not translating from its own English output."
        keys = list(VARIETY_SCHEMA["properties"]["glosses"]["items"]["properties"])
        assert keys.index("glossDe") < keys.index("glossEn")

    def test_requires_the_fields_an_answer_is_useless_without(self) -> None:
        required = VARIETY_SCHEMA["properties"]["glosses"]["items"]["required"]
        assert {"lemma", "pos", "glossDe", "glossEn", "variety", "register"} <= set(required)


class TestTheSystemPrompt:
    def test_names_the_home_dialect(self) -> None:
        # CLAUDE.md §5: homeDialect governs regional rendering and is never
        # hard-coded. "Is this regional" has no answer until you say
        # regional relative to what.
        mx = build_system_prompt(Variety.MX)
        assert "es-MX" in mx and "Mexico" in mx

    def test_a_different_home_dialect_changes_the_instructions(self) -> None:
        mx = build_system_prompt(Variety.MX)
        ar = build_system_prompt(Variety.AR)
        assert mx != ar
        assert "Argentina" in ar
        assert "es-AR" in ar

    def test_states_the_null_home_equivalent_rule(self) -> None:
        # §7.5: "if the term is pan-Hispanic, variety must be general and
        # homeEquivalent must be null."
        prompt = build_system_prompt(Variety.MX)
        assert "must** be null" in prompt or "must be null" in prompt

    def test_teaches_the_negative_case_too(self) -> None:
        # Over-tagging is the expected failure, so the prompt has to spend
        # words on words that are *not* regional — the harder half.
        prompt = build_system_prompt(Variety.MX)
        assert "Not regional" in prompt
        assert "amor" in prompt

    def test_says_what_to_do_when_unsure(self) -> None:
        prompt = build_system_prompt(Variety.MX)
        assert "unsure" in prompt.lower()


class TestParsingAGoodAnswer:
    def test_builds_both_the_gloss_and_the_sense(self) -> None:
        parser = VarietyParser(home_dialect=Variety.MX)
        gloss, shortened = parser(answer(), CORAZON)

        assert gloss.de == "das Herz"
        assert gloss.en == "heart"
        assert not shortened

        sense = parser.senses[("corazón", "NOUN")]
        assert sense.variety is Variety.GENERAL
        assert sense.register is Register.NEUTRAL
        assert sense.confidence == 0.98

    def test_keeps_a_foreign_variety_and_its_home_equivalent(self) -> None:
        parser = VarietyParser(home_dialect=Variety.MX)
        parser(
            answer(
                lemma="pibe",
                glossDe="der Junge",
                glossEn="kid",
                variety="es-AR",
                register="coloquial",
                homeEquivalent="chavo",
                homeEquivalentNote="In Mexiko sagt man 'chavo'.",
            ),
            PIBE,
        )
        sense = parser.senses[("pibe", "NOUN")]
        assert sense.variety is Variety.AR
        assert sense.register is Register.COLOQUIAL
        assert sense.home_equivalent == "chavo"
        assert sense.needs_badge(Variety.MX)

    def test_carries_regional_into_the_gloss_mexicanism_field(self) -> None:
        # SPEC §5's teach rule promotes a regional word below the frequency
        # floor. For a pan-Hispanic rotation the useful reading of that field
        # is "regional", not "Mexican".
        parser = VarietyParser(home_dialect=Variety.MX)
        general, _ = parser(answer(), CORAZON)
        regional, _ = parser(answer(lemma="pibe", variety="es-AR"), PIBE)

        assert general.mexicanism is False
        assert regional.mexicanism is True
        assert regional.region_note is not None and "AR" in regional.region_note

    def test_a_region_note_exists_whenever_mexicanism_is_true(self) -> None:
        # Gloss.__post_init__ treats the pair as an invariant and fills a
        # default if the note is missing, which would hide the real label.
        parser = VarietyParser(home_dialect=Variety.MX)
        gloss, _ = parser(answer(lemma="pibe", variety="es-AR"), PIBE)
        assert gloss.mexicanism and gloss.region_note


class TestRefusingToBelieveTheAnswer:
    def test_a_home_equivalent_on_a_general_sense_is_dropped(self) -> None:
        # The expected model failure, defended in code rather than asked for.
        parser = VarietyParser(home_dialect=Variety.MX)
        parser(answer(variety="general", homeEquivalent="chavo"), CORAZON)
        assert parser.senses[("corazón", "NOUN")].home_equivalent is None

    def test_a_home_equivalent_on_a_home_dialect_sense_is_dropped(self) -> None:
        parser = VarietyParser(home_dialect=Variety.MX)
        parser(answer(variety="es-MX", homeEquivalent="morro"), CORAZON)
        assert parser.senses[("corazón", "NOUN")].home_equivalent is None

    def test_an_invented_variety_becomes_general(self) -> None:
        parser = VarietyParser(home_dialect=Variety.MX)
        parser(answer(variety="es-419"), CORAZON)
        assert parser.senses[("corazón", "NOUN")].variety is Variety.GENERAL

    def test_an_answer_for_the_wrong_lemma_is_rejected(self) -> None:
        parser = VarietyParser(home_dialect=Variety.MX)
        with pytest.raises(Rejected):
            parser(answer(lemma="casona"), CORAZON)

    def test_the_prompts_own_separator_is_forgiven_in_the_echo(self) -> None:
        # gemma3 echoes the whole rendered line back. Rejecting a good answer
        # over a separator this code put there is a self-inflicted miss.
        parser = VarietyParser(home_dialect=Variety.MX)
        gloss, _ = parser(answer(lemma="corazón · NOUN"), CORAZON)
        assert gloss.de == "das Herz"

    def test_a_definition_instead_of_a_gloss_is_rejected_while_a_retry_remains(
        self,
    ) -> None:
        parser = VarietyParser(home_dialect=Variety.MX)
        with pytest.raises(Rejected):
            parser(
                answer(glossDe="das Organ, das das Blut durch den Körper pumpt"),
                CORAZON,
                strict=True,
            )

    def test_and_is_kept_on_the_last_attempt_only_if_merely_trimmed(self) -> None:
        parser = VarietyParser(home_dialect=Variety.MX)
        gloss, shortened = parser(
            answer(glossDe="das Herz, der Kern, die Mitte, das Innere"),
            CORAZON,
            strict=False,
        )
        assert shortened
        assert gloss.de is not None and gloss.de.count(",") <= 2

    def test_not_spanish_forces_both_glosses_null(self) -> None:
        parser = VarietyParser(home_dialect=Variety.MX)
        gloss, _ = parser(
            answer(lemma="acaeceír", pos="VERB", glossDe="geschehen", notSpanish=True),
            GlossTask(lemma="acaeceír", pos="VERB"),
        )
        assert gloss.not_spanish
        assert gloss.de is None and gloss.en is None

    def test_a_non_object_answer_is_rejected(self) -> None:
        parser = VarietyParser(home_dialect=Variety.MX)
        with pytest.raises(Rejected):
            parser("not an object", CORAZON)

    @pytest.mark.parametrize("value", [None, "high", [], {}])
    def test_a_junk_confidence_becomes_none_rather_than_raising(
        self, value: object
    ) -> None:
        parser = VarietyParser(home_dialect=Variety.MX)
        parser(answer(confidence=value), CORAZON)
        assert parser.senses[("corazón", "NOUN")].confidence is None


class TestTheCorrection:
    def test_restates_rocolas_rules_not_molcajetes(self) -> None:
        # A correction naming the wrong rules invites the model to answer a
        # question about mexicanisms when it was asked about varieties.
        text = render_correction(
            [{"lemma": "corazón", "pos": "NOUN"}],
            offending='{"variety": "es-419"}',
            reason="unknown variety",
        )
        assert "variety" in text
        assert "homeEquivalent" in text
        assert "mexicanism" not in text

    def test_quotes_the_offending_answer_back(self) -> None:
        text = render_correction(
            [{"lemma": "corazón", "pos": "NOUN"}],
            offending="SOMETHING BAD",
            reason="a reason",
        )
        assert "SOMETHING BAD" in text
        assert "a reason" in text

    def test_repeats_the_question(self) -> None:
        # A correction that omits the question invites an answer to the
        # complaint instead.
        text = render_correction(
            [{"lemma": "corazón", "pos": "NOUN"}], offending="x", reason="y"
        )
        assert "corazón" in text

    def test_truncates_a_huge_offending_body(self) -> None:
        text = render_correction(
            [{"lemma": "x", "pos": "NOUN"}], offending="z" * 5000, reason="y"
        )
        assert len(text) < 2000


def test_prompt_version_is_recorded() -> None:
    # Stored on every cached row, so a prompt change is tellable from a stale
    # row without re-inferring everything.
    assert isinstance(PROMPT_VERSION, int)
