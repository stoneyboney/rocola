"""SPEC §8.2's scoring, and CLAUDE.md §9's refusal to auto-accept below 0.85."""

from __future__ import annotations

import pytest

from rocola_prep.matcher.score import (
    ACCEPT_THRESHOLD,
    REVIEW_THRESHOLD,
    Verdict,
    duration_similarity,
    score_candidate,
    token_set_ratio,
    verdict_for,
)


class TestTokenSetRatio:
    def test_identical_is_one(self) -> None:
        assert token_set_ratio("como la flor", "como la flor") == 1.0

    def test_word_order_does_not_matter(self) -> None:
        # The reason it is a *set* ratio. Scrobblers reorder; catalogues reorder.
        assert token_set_ratio("la bamba", "bamba la") == 1.0

    def test_extra_words_cost_little(self) -> None:
        # A candidate carrying an album suffix the scrobble lacks is still the
        # same song, and must outscore the review threshold comfortably.
        assert token_set_ratio(
            "corazon espinado", "corazon espinado remasterizado"
        ) > 0.8

    def test_unrelated_is_low(self) -> None:
        assert token_set_ratio("como la flor", "bohemian rhapsody") < 0.4

    def test_both_empty_is_one_and_one_empty_is_zero(self) -> None:
        # Degenerate, but reachable: a title that was entirely a qualifier
        # normalises to "".
        assert token_set_ratio("", "") == 1.0
        assert token_set_ratio("como la flor", "") == 0.0
        assert token_set_ratio("", "como la flor") == 0.0

    def test_is_symmetric(self) -> None:
        a, b = "ven conmigo", "conmigo ven ahora"
        assert token_set_ratio(a, b) == pytest.approx(token_set_ratio(b, a))


class TestDurationSimilarity:
    @pytest.mark.parametrize("candidate", [129.0, 130.0, 132.0, 126.0])
    def test_full_credit_within_three_seconds(self, candidate: float) -> None:
        assert duration_similarity(129.0, candidate) == 1.0

    def test_decays_beyond_the_tolerance(self) -> None:
        near = duration_similarity(129.0, 140.0)
        far = duration_similarity(129.0, 155.0)
        assert near is not None and far is not None
        assert 0.0 < far < near < 1.0

    def test_floors_at_zero_rather_than_going_negative(self) -> None:
        assert duration_similarity(129.0, 600.0) == 0.0

    @pytest.mark.parametrize(
        "scrobbled,candidate",
        [(None, 129.0), (129.0, None), (None, None), (0.0, 129.0), (129.0, 0.0)],
    )
    def test_unknown_is_none_not_zero(
        self, scrobbled: float | None, candidate: float | None
    ) -> None:
        # "Unknown" and "known and completely wrong" must not collapse into one
        # value — the first redistributes the weight, the second penalises.
        assert duration_similarity(scrobbled, candidate) is None


class TestScoring:
    def test_a_perfect_match_accepts(self) -> None:
        result = score_candidate(
            title_key="como la flor",
            artist_key="selena",
            candidate_title_key="como la flor",
            candidate_artist_key="selena",
            scrobbled_duration=190.0,
            candidate_duration=190.0,
        )
        assert result.score == pytest.approx(1.0)
        assert result.verdict is Verdict.ACCEPT

    def test_the_weights_are_the_ones_spec_8_2_gives(self) -> None:
        # Title perfect, artist nothing in common, duration perfect:
        # 0.5*1 + 0.35*0 + 0.15*1 = 0.65
        result = score_candidate(
            title_key="como la flor",
            artist_key="selena",
            candidate_title_key="como la flor",
            candidate_artist_key="xyz",
            scrobbled_duration=190.0,
            candidate_duration=190.0,
        )
        assert result.score == pytest.approx(0.65, abs=0.02)

    def test_a_wrong_song_by_the_right_artist_is_rejected(self) -> None:
        # The failure mode that matters: same artist, different track. Accepting
        # this attaches the wrong lyrics to the right-looking row.
        result = score_candidate(
            title_key="como la flor",
            artist_key="selena",
            candidate_title_key="bidi bidi bom bom",
            candidate_artist_key="selena",
        )
        assert result.verdict is Verdict.REJECT

    def test_a_near_miss_goes_to_review_not_accept(self) -> None:
        # 0.748: title similar but not the same words, artist a subset.
        result = score_candidate(
            title_key="ven conmigo",
            artist_key="selena",
            candidate_title_key="ben comigo",
            candidate_artist_key="selena y los dinos",
        )
        assert result.verdict is Verdict.REVIEW
        assert REVIEW_THRESHOLD <= result.score < ACCEPT_THRESHOLD


class TestTheSubsetHazard:
    """A property of §8.2's algorithm that the probe has to measure.

    `token_set_ratio` scores 1.0 whenever one side's tokens are a **subset** of
    the other's — that is what makes it forgiving of album suffixes, and it is
    the documented behaviour of the algorithm SPEC §8.2 names by name. rapidfuzz
    does the same thing; this is not an artefact of writing it out by hand.

    The cost is that a medley swallows its parts. `Ven Conmigo` is a strict
    token-subset of `Ven Conmigo / Perdóname`, so it scores a perfect 1.0
    against a different recording, and `selena` does the same against `selena y
    los dinos`. The combined score is 1.0 and the match auto-accepts — exactly
    the silent mismatch CLAUDE.md §9 says is worse than no lyric at all.

    Both of those medleys are in the rotation this was built against, so the
    case is real rather than theoretical. It is pinned rather than fixed:
    changing the algorithm would be inventing where the spec is not silent, so
    the coverage probe counts subset-accepts instead and the number decides
    whether §8.2 needs revisiting.
    """

    def test_a_subset_title_scores_a_perfect_one(self) -> None:
        assert token_set_ratio("ven conmigo", "ven conmigo perdoname") == 1.0

    def test_a_subset_artist_scores_a_perfect_one(self) -> None:
        assert token_set_ratio("selena", "selena y los dinos") == 1.0

    def test_and_so_a_medley_auto_accepts(self) -> None:
        result = score_candidate(
            title_key="ven conmigo",
            artist_key="selena",
            candidate_title_key="ven conmigo perdoname",
            candidate_artist_key="selena y los dinos",
        )
        assert result.score == pytest.approx(1.0)
        assert result.verdict is Verdict.ACCEPT

    def test_a_repeated_word_collides_too(self) -> None:
        # The same hazard wearing a different hat: a token *set* drops
        # duplicates, so "bom bom" and "bom" are the same set and score 1.0.
        # Selena has both `Bidi Bidi Bom Bom` and shortened catalogue entries.
        assert token_set_ratio("bidi bidi bom bom", "bidi bidi bom") == 1.0

    def test_is_detectable_without_changing_the_score(self) -> None:
        # What the probe counts. Subset-or-equal rather than strict subset,
        # so that the repeated-word collision above is caught as well, and
        # only flagged when the strings themselves actually differ.
        def collides(a: str, b: str) -> bool:
            sa, sb = set(a.split()), set(b.split())
            return a != b and (sa <= sb or sb <= sa)

        assert collides("ven conmigo", "ven conmigo perdoname")
        assert collides("bidi bidi bom bom", "bidi bidi bom")
        assert not collides("como la flor", "como la flor")
        assert not collides("como la flor", "bidi bidi bom bom")


class TestDurationRedistribution:
    def test_an_unknown_duration_can_still_reach_accept(self) -> None:
        # The bug this guards: scoring an unknown duration as zero caps a
        # perfect title-and-artist match at 0.85 exactly, and every track
        # without a duration lands in the manual queue for no reason to do with
        # how well it matched. Most scrobbles have no duration.
        result = score_candidate(
            title_key="como la flor",
            artist_key="selena",
            candidate_title_key="como la flor",
            candidate_artist_key="selena",
        )
        assert result.duration_similarity is None
        assert result.score == pytest.approx(1.0)
        assert result.verdict is Verdict.ACCEPT

    def test_redistribution_preserves_the_title_artist_balance(self) -> None:
        # Title perfect, artist nothing: 0.5/(0.5+0.35) = 0.588…
        result = score_candidate(
            title_key="como la flor",
            artist_key="selena",
            candidate_title_key="como la flor",
            candidate_artist_key="xyz",
        )
        assert result.score == pytest.approx(0.5 / 0.85, abs=0.02)

    def test_a_known_bad_duration_still_penalises(self) -> None:
        with_bad = score_candidate(
            title_key="como la flor",
            artist_key="selena",
            candidate_title_key="como la flor",
            candidate_artist_key="selena",
            scrobbled_duration=190.0,
            candidate_duration=600.0,
        )
        without = score_candidate(
            title_key="como la flor",
            artist_key="selena",
            candidate_title_key="como la flor",
            candidate_artist_key="selena",
        )
        assert with_bad.score < without.score


class TestThresholds:
    @pytest.mark.parametrize(
        "score,expected",
        [
            (1.0, Verdict.ACCEPT),
            (0.851, Verdict.ACCEPT),
            (0.85, Verdict.ACCEPT),
            (0.849, Verdict.REVIEW),
            (0.70, Verdict.REVIEW),
            (0.699, Verdict.REJECT),
            (0.0, Verdict.REJECT),
        ],
    )
    def test_the_boundaries_are_where_spec_8_2_puts_them(
        self, score: float, expected: Verdict
    ) -> None:
        assert verdict_for(score) is expected

    def test_nothing_below_the_accept_threshold_is_ever_accepted(self) -> None:
        # CLAUDE.md §9, stated as a property rather than a boundary case,
        # because this is the rule the whole middle band exists to enforce.
        for i in range(1000):
            score = i / 1000
            if verdict_for(score) is Verdict.ACCEPT:
                assert score >= ACCEPT_THRESHOLD
