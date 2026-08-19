"""SPEC §6.2 and §7.4 steps 1–3, on synthetic Spanish.

Every lyric here is invented for the test (CLAUDE.md §2). They are deliberately
dull: the structure is the subject, not the words.
"""

from __future__ import annotations

import pytest

from rocola_prep.teachset.stanzas import (
    Line,
    line_key,
    parse_document,
)

# One verse, one chorus, another verse, the chorus again. Synthetic.
SONG = """\
Camino solo por la sierra
la luna alumbra mi cantar

Ay corazón, no llores más
ay corazón, ya vuelvo a casa

El viento lleva mi bandera
y el cerro me ve pasar

Ay corazón, no llores más
ay corazón, ya vuelvo a casa
"""


class TestStanzaSplitting:
    def test_blank_lines_delimit_stanzas(self) -> None:
        doc = parse_document(SONG)
        assert len(doc.stanzas) == 4
        assert [len(s.lines) for s in doc.stanzas] == [2, 2, 2, 2]

    def test_line_breaks_are_preserved_exactly(self) -> None:
        # §10.1: lyrics are not prose and must never be reflowed.
        doc = parse_document(SONG)
        assert doc.stanzas[0].lines[0].text == "Camino solo por la sierra"
        assert doc.stanzas[0].lines[1].text == "la luna alumbra mi cantar"

    def test_runs_of_blank_lines_collapse(self) -> None:
        # LRCLIB submissions are inconsistent about spacing, and an empty
        # stanza is not something the reader can render.
        doc = parse_document("Una línea\n\n\n\n\nOtra línea\n")
        assert len(doc.stanzas) == 2

    def test_leading_and_trailing_blank_lines_produce_no_stanza(self) -> None:
        doc = parse_document("\n\n\nUna línea\n\n\n")
        assert len(doc.stanzas) == 1

    def test_line_indices_are_global_across_the_document(self) -> None:
        # SPEC §6.2: "global line index within the document".
        doc = parse_document(SONG)
        assert [line.index for line in doc.lines] == list(range(8))

    def test_empty_input_is_an_empty_document(self) -> None:
        doc = parse_document("")
        assert doc.stanzas == ()
        assert doc.lines == ()
        assert doc.unique_lines == ()


class TestTheLineKey:
    @pytest.mark.parametrize(
        "a,b",
        [
            ("Ay corazón", "ay corazon"),
            ("¡Ay, corazón!", "Ay corazón"),
            ("Ay   corazón  ", "ay corazón"),
            ("¿Ay corazón?", "Ay corazón"),
            ("Ay — corazón", "Ay corazón"),
        ],
    )
    def test_folds_case_accents_punctuation_and_spacing(self, a: str, b: str) -> None:
        # §7.4 step 1. A chorus written slightly differently the second time is
        # still the same chorus.
        assert line_key(a) == line_key(b)

    def test_keeps_elided_forms_intact(self) -> None:
        # `pa'` and `nomás` matter; only the apostrophe goes, not the letters.
        assert line_key("pa' la casa") == "pa la casa"
        assert line_key("nomás") == "nomas"

    def test_different_lines_get_different_keys(self) -> None:
        assert line_key("la luna") != line_key("el sol")

    def test_a_punctuation_only_line_folds_to_nothing(self) -> None:
        assert line_key("...") == ""
        assert line_key("— — —") == ""


class TestRepeatDetection:
    def test_the_repeated_chorus_lines_are_marked(self) -> None:
        doc = parse_document(SONG)
        lines = doc.lines
        # Lines 2,3 are the chorus; 6,7 are it again.
        assert not lines[2].is_repeat
        assert not lines[3].is_repeat
        assert lines[6].repeat_of == 2
        assert lines[7].repeat_of == 3

    def test_the_repeated_stanza_is_marked_at_stanza_level(self) -> None:
        # §7.4 step 3, and what §10.1's reader de-emphasises.
        doc = parse_document(SONG)
        assert doc.stanzas[1].repeat_of is None
        assert doc.stanzas[3].repeat_of == 1
        assert doc.repeated_stanza_count == 1

    def test_a_stanza_is_not_a_repeat_when_only_some_lines_are(self) -> None:
        song = "Una línea\notra línea\n\nUna línea\ntercera línea\n"
        doc = parse_document(song)
        assert doc.stanzas[1].repeat_of is None
        assert doc.lines[2].repeat_of == 0
        assert not doc.lines[3].is_repeat

    def test_case_and_punctuation_do_not_defeat_repeat_detection(self) -> None:
        song = "¡Ay, corazón!\n\nay corazon\n"
        doc = parse_document(song)
        assert doc.lines[1].repeat_of == 0

    def test_punctuation_only_lines_are_not_repeats_of_each_other(self) -> None:
        # They all fold to "", and treating them as one line would be an
        # accident of the folding rather than a fact about the song.
        doc = parse_document("...\n\nUna línea\n\n...\n")
        assert not doc.lines[0].is_repeat
        assert not doc.lines[2].is_repeat


class TestUniqueLines:
    def test_is_first_occurrence_in_document_order(self) -> None:
        doc = parse_document(SONG)
        assert [line.index for line in doc.unique_lines] == [0, 1, 2, 3, 4, 5]

    def test_a_chorus_sung_four_times_contributes_once(self) -> None:
        # The property the whole module exists for.
        chorus = "Ay corazón, no llores más\nay corazón, ya vuelvo a casa"
        verse = "Camino solo por la sierra\nla luna alumbra mi cantar"
        once = parse_document(f"{verse}\n\n{chorus}\n")
        four = parse_document(f"{verse}\n\n{chorus}\n\n{chorus}\n\n{chorus}\n\n{chorus}\n")

        assert len(four.lines) == 10
        assert len(once.lines) == 4
        assert [line.text for line in four.unique_lines] == [
            line.text for line in once.unique_lines
        ]
        assert four.repeated_line_count == 6

    def test_a_song_with_no_repeats_is_unchanged_by_deduplication(self) -> None:
        doc = parse_document(
            "Camino solo por la sierra\n\nla luna alumbra mi cantar\n\n"
            "el viento lleva mi bandera\n"
        )
        assert len(doc.unique_lines) == len(doc.lines) == 3

    def test_a_partly_repeated_stanza_dedupes_only_its_repeated_lines(self) -> None:
        # Changing one line of the second chorus leaves the other one a repeat,
        # so 7 unique of 8 — not 8, and not 6.
        doc = parse_document(SONG.replace("ya vuelvo a casa", "me voy de casa", 1))
        assert len(doc.lines) == 8
        assert len(doc.unique_lines) == 7
        assert doc.stanzas[3].repeat_of is None


class TestLineRecord:
    def test_carries_the_fetched_text_untouched(self) -> None:
        line = parse_document("  ¡Ay, corazón!  \n").lines[0]
        assert line.text == "  ¡Ay, corazón!  "
        assert line.key == "ay corazon"

    def test_is_blank_reflects_the_key_not_the_text(self) -> None:
        assert parse_document("...\n").lines[0].is_blank
        assert not parse_document("Una línea\n").lines[0].is_blank

    def test_is_frozen(self) -> None:
        line = parse_document("Una línea\n").lines[0]
        assert isinstance(line, Line)
        with pytest.raises(Exception):
            line.text = "mutated"  # type: ignore[misc]
