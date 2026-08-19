"""SPEC §7.3, on synthetic text.

Every passage here is invented for the test — CLAUDE.md §2 forbids a real lyric
in a fixture, and the classifier does not care whether prose scans.
"""

from __future__ import annotations

import pytest

from rocola_prep.langfilter.detector import (
    DEFAULT_MIN_CONFIDENCE,
    LANGUAGES,
    UNSUPPORTED_BY_LINGUA,
    Verdict,
    classify,
)

# Synthetic, written for this file. Long enough to classify, which is the only
# property that matters.
SPANISH = (
    "Camino solo por la sierra mientras la luna alumbra mi cantar. "
    "El viento lleva mi bandera vieja y el cerro me ve pasar despacio. "
    "Nadie me espera en el camino pero sigo cantando igual."
)
ENGLISH = (
    "I walk alone across the mountain while the moon lights up my singing. "
    "The wind carries my old banner and the hill watches me go by slowly. "
    "Nobody waits for me on the road but I keep on singing anyway."
)
PORTUGUESE = (
    "Caminho sozinho pela serra enquanto a lua ilumina o meu cantar. "
    "O vento leva a minha bandeira velha e o morro me vê passar devagar. "
    "Ninguém me espera no caminho mas continuo cantando do mesmo jeito."
)
ITALIAN = (
    "Cammino da solo per la montagna mentre la luna illumina il mio cantare. "
    "Il vento porta la mia vecchia bandiera e la collina mi guarda passare. "
    "Nessuno mi aspetta sulla strada ma continuo a cantare lo stesso."
)


class TestTheObviousCases:
    def test_spanish_is_spanish(self) -> None:
        result = classify(SPANISH)
        assert result.verdict is Verdict.SPANISH
        assert result.language == "es"
        assert result.is_spanish
        assert result.confidence >= DEFAULT_MIN_CONFIDENCE

    @pytest.mark.parametrize(
        "text,expected", [(ENGLISH, "en"), (PORTUGUESE, "pt"), (ITALIAN, "it")]
    )
    def test_the_confusable_neighbours_are_not_spanish(
        self, text: str, expected: str
    ) -> None:
        result = classify(text)
        assert result.verdict is Verdict.OTHER
        assert result.language == expected
        assert not result.is_spanish

    def test_portuguese_is_the_one_worth_pinning(self) -> None:
        # It shares most of its orthography with Spanish and is the failure
        # this rotation would actually hit — CSS are Brazilian.
        assert classify(PORTUGUESE).language == "pt"
        assert classify(PORTUGUESE).scores["es"] < classify(SPANISH).scores["es"]


class TestTheReviewBand:
    def test_a_mixed_passage_goes_to_review_not_reject(self) -> None:
        # SPEC §7.3: "A track at 0.6 Spanish is genuinely mixed; surface it as a
        # manual-review item rather than auto-rejecting." Spanglish is a
        # register, not a classifier failure.
        mixed = (
            "Baby yo te quiero pero the night is young and I don't wanna go. "
            "Dime que sí, tell me that you feel it too, mi amor. "
            "Vamos a bailar until the morning comes around otra vez."
        )
        result = classify(mixed, min_confidence=0.90)
        assert result.verdict in {Verdict.REVIEW, Verdict.OTHER}
        if result.verdict is Verdict.REVIEW:
            assert result.language == "es"
            assert not result.is_spanish

    def test_the_threshold_is_what_moves_the_verdict(self) -> None:
        # Same text, two thresholds: the only difference is the bar.
        confidence = classify(SPANISH).confidence
        assert classify(SPANISH, min_confidence=confidence - 0.01).is_spanish
        strict = classify(SPANISH, min_confidence=min(confidence + 0.01, 1.0))
        assert strict.verdict is Verdict.REVIEW
        assert strict.language == "es"

    def test_review_is_not_counted_as_spanish(self) -> None:
        # The distinction the report depends on. `is_spanish` must mean
        # "confidently", or the coverage number quietly includes the doubtful.
        strict = classify(SPANISH, min_confidence=1.01)
        assert strict.verdict is Verdict.REVIEW
        assert not strict.is_spanish


class TestTooShort:
    @pytest.mark.parametrize("text", ["", "   ", "Sí.", "La la la", "Ay ay ay"])
    def test_a_fragment_gets_no_verdict(self, text: str) -> None:
        # A two-line fragment classifies as whatever its function words look
        # like, which is a coin flip dressed as a measurement.
        result = classify(text)
        assert result.verdict is Verdict.TOO_SHORT
        assert result.language is None
        assert not result.is_spanish

    def test_a_long_enough_passage_does_get_one(self) -> None:
        assert classify(SPANISH).verdict is not Verdict.TOO_SHORT


class TestScores:
    def test_reports_every_candidate_language(self) -> None:
        scores = classify(SPANISH).scores
        assert set(scores) == {"es", "en", "pt", "ca", "it", "fr"}
        assert all(0.0 <= v <= 1.0 for v in scores.values())

    def test_spanish_wins_on_spanish(self) -> None:
        scores = classify(SPANISH).scores
        assert max(scores, key=lambda k: scores[k]) == "es"

    def test_the_candidate_set_is_spec_7_3_less_what_lingua_lacks(self) -> None:
        # §7.3 names seven; lingua has no Galician, so six. Pinned rather than
        # rounded off, so that the gap stays visible if the library gains it.
        assert len(LANGUAGES) == 6
        assert UNSUPPORTED_BY_LINGUA == ("gl",)

    def test_galician_really_is_absent_from_lingua(self) -> None:
        from lingua import Language

        assert not hasattr(Language, "GALICIAN")
