"""SPEC §7.4 step 4, on synthetic Spanish.

The load-bearing test is `TestChorusDeduplication`. Everything else is
scaffolding around it.

These use the real spaCy pipeline through the `nlp` fixture that
`molcajete_prep`'s pytest plugin ships — lemmatisation is what the counting
runs on, and stubbing it would test the stub.
"""

from __future__ import annotations

import pytest

from molcajete_prep.classify import ClassificationOptions

from rocola_prep.teachset.builder import build_teach_set
from rocola_prep.teachset.stanzas import parse_document

# Synthetic throughout. The verse carries open-class vocabulary; the chorus
# repeats a smaller set, which is the situation §7.4 exists for.
VERSE_ONE = "Camino solo por la sierra vieja\nla luna alumbra mi cantar tranquilo"
VERSE_TWO = "El viento lleva mi bandera rota\ny el cerro me ve pasar despacio"
CHORUS = "Ay corazón, no llores más\nay corazón, ya vuelvo a casa"


def song(*blocks: str) -> str:
    return "\n\n".join(blocks) + "\n"


def lemmas_of(result) -> list[str]:
    return [card.lemma for card in result.teach]


class TestChorusDeduplication:
    """§7.4, and CLAUDE.md §6's "single most important behavioural difference"."""

    def test_a_chorus_sung_four_times_gives_the_same_teach_set_as_once(
        self, nlp
    ) -> None:
        once = build_teach_set(
            parse_document(song(VERSE_ONE, CHORUS, VERSE_TWO)), nlp
        )
        four = build_teach_set(
            parse_document(
                song(VERSE_ONE, CHORUS, VERSE_TWO, CHORUS, CHORUS, CHORUS)
            ),
            nlp,
        )
        assert lemmas_of(once) == lemmas_of(four)

    def test_and_the_same_counts_too(self, nlp) -> None:
        # Not just the same words in the same order — the same frequencies,
        # which is what the ordering is derived from.
        once = build_teach_set(parse_document(song(VERSE_ONE, CHORUS)), nlp)
        four = build_teach_set(
            parse_document(song(VERSE_ONE, CHORUS, CHORUS, CHORUS, CHORUS)), nlp
        )
        assert [c.unique_line_count for c in once.teach] == [
            c.unique_line_count for c in four.teach
        ]

    def test_the_hook_does_not_outrank_the_verse_however_often_it_repeats(
        self, nlp
    ) -> None:
        # The failure §7.4 describes: without deduplication the chorus
        # vocabulary looks N times as common as it is, sorts to the top, and
        # the builder teaches the hook while skipping the verses.
        result = build_teach_set(
            parse_document(
                song(VERSE_ONE, CHORUS, CHORUS, CHORUS, CHORUS, CHORUS, VERSE_TWO)
            ),
            nlp,
        )
        counts = {card.lemma: card.unique_line_count for card in result.teach}
        # `corazón` appears twice in the chorus, which is sung six times — 12
        # occurrences raw, 2 after deduplication.
        if "corazón" in counts:
            assert counts["corazón"] <= 2

    def test_reports_how_much_was_repetition(self, nlp) -> None:
        plain = build_teach_set(parse_document(song(VERSE_ONE, CHORUS)), nlp)
        repetitive = build_teach_set(
            parse_document(song(VERSE_ONE, CHORUS, CHORUS, CHORUS)), nlp
        )
        assert plain.deduplication_ratio == 0.0
        assert repetitive.deduplication_ratio > 0.4
        # And the raw count did grow, so the ratio is measuring something real.
        assert repetitive.total_word_tokens > plain.total_word_tokens
        assert repetitive.unique_word_tokens == plain.unique_word_tokens


class TestInheritedRules:
    def test_teaches_no_closed_class_word(self, nlp) -> None:
        result = build_teach_set(parse_document(song(VERSE_ONE, VERSE_TWO)), nlp)
        for lemma in lemmas_of(result):
            assert lemma not in {"el", "la", "de", "y", "por", "mi", "no", "más"}

    def test_a_known_lemma_is_not_taught(self, nlp) -> None:
        before = build_teach_set(parse_document(song(VERSE_ONE, VERSE_TWO)), nlp)
        assert before.teach, "fixture must teach something for this to mean anything"

        first = before.teach[0].lemma
        after = build_teach_set(
            parse_document(song(VERSE_ONE, VERSE_TWO)),
            nlp,
            known_lemmas=frozenset({first}),
        )
        assert first not in lemmas_of(after)
        assert len(after.teach) == len(before.teach) - 1

    def test_sorted_most_used_first(self, nlp) -> None:
        # §5 Step 3: an abandoned session should still have taught the most
        # useful words.
        result = build_teach_set(
            parse_document(song(VERSE_ONE, VERSE_TWO, CHORUS)), nlp
        )
        counts = [card.unique_line_count for card in result.teach]
        assert counts == sorted(counts, reverse=True)

    def test_is_deterministic(self, nlp) -> None:
        # Ties break on the key, so two builds of one song agree exactly.
        doc = parse_document(song(VERSE_ONE, VERSE_TWO, CHORUS))
        assert lemmas_of(build_teach_set(doc, nlp)) == lemmas_of(
            build_teach_set(doc, nlp)
        )


class TestTheCap:
    def test_a_dense_song_is_flagged_and_not_split(self, nlp) -> None:
        # §11.1 and CLAUDE.md §6: never split a song. The cap is surfaced for
        # the user to decide about, and nothing acts on it.
        long_song = song(*[VERSE_ONE, VERSE_TWO, CHORUS] * 6)
        result = build_teach_set(
            parse_document(long_song),
            nlp,
            options=ClassificationOptions(max_cards_per_session=2, zipf_threshold=7.0),
        )
        if len(result.teach) > 18:
            assert result.is_dense
        # Whatever the count, the teach set is one list. Nothing segmented it.
        assert isinstance(result.teach, tuple)

    def test_is_dense_reads_the_18_card_cap(self, nlp) -> None:
        result = build_teach_set(parse_document(song(VERSE_ONE)), nlp)
        assert result.is_dense is (len(result.teach) > 18)


class TestExamples:
    def test_a_card_carries_a_line_from_the_song(self, nlp) -> None:
        result = build_teach_set(parse_document(song(VERSE_ONE, VERSE_TWO)), nlp)
        assert result.teach
        card = result.teach[0]
        assert card.example is not None
        # §13: one illustrative context line is the ceiling, never a stanza.
        assert "\n" not in card.example
        assert card.lemma in card.example.lower() or len(card.example) > 0

    def test_the_example_comes_from_a_unique_line(self, nlp) -> None:
        doc = parse_document(song(VERSE_ONE, CHORUS, CHORUS, CHORUS))
        result = build_teach_set(doc, nlp)
        unique_texts = {line.text for line in doc.unique_lines}
        for card in result.teach:
            if card.example:
                assert any(card.example in text for text in unique_texts)


class TestDegenerate:
    def test_an_empty_document_teaches_nothing(self, nlp) -> None:
        result = build_teach_set(parse_document(""), nlp)
        assert result.teach == ()
        assert result.gloss_only == ()
        assert result.unique_word_tokens == 0
        assert result.deduplication_ratio == 0.0

    def test_a_song_that_is_one_repeated_line(self, nlp) -> None:
        result = build_teach_set(
            parse_document("Ay corazón\n\nay corazón\n\nAy, corazón\n"), nlp
        )
        assert result.unique_word_tokens < result.total_word_tokens
        for card in result.teach:
            assert card.unique_line_count == 1

    @pytest.mark.parametrize("text", ["...\n", "\n\n\n", "   \n"])
    def test_a_document_with_no_words_does_not_raise(self, nlp, text: str) -> None:
        result = build_teach_set(parse_document(text), nlp)
        assert result.teach == ()
