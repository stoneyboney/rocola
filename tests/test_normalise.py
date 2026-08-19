"""SPEC §8.1, rule by rule.

The cases with real titles in them are titles, not lyrics — CLAUDE.md §2 is
about lyric text, and a track name is what the matcher exists to handle. They
are drawn from the rotation this was built against because inventing scrobbles
would mean inventing their messiness too, and the messiness is the subject.
"""

from __future__ import annotations

import pytest

from rocola_prep.matcher.normalise import (
    fold_accents,
    normalise,
    normalise_artist,
    normalise_title,
)


class TestRule1CaseAndForm:
    def test_lowercases_and_normalises_unicode(self) -> None:
        assert normalise_title("Como La Flor") == "como la flor"

    def test_nfkc_folds_compatibility_forms(self) -> None:
        # A fullwidth or ligature form arrives from some scrobblers and must
        # compare equal to the plain one.
        assert normalise_title("Ｃｏｍｏ") == "como"


class TestRule2Qualifiers:
    @pytest.mark.parametrize(
        "title",
        [
            "Como La Flor (Remastered)",
            "Como La Flor (Remastered 2026)",
            "Como La Flor (2026 Remaster)",
            "Como La Flor (Live)",
            "Como La Flor (En Vivo)",
            "Como La Flor (Single Version)",
            "Como La Flor (Album Version)",
            "Como La Flor (Radio Edit)",
            "Como La Flor (Bonus Track)",
            "Como La Flor (Deluxe)",
            "Como La Flor (Explicit)",
            "Como La Flor (Mono)",
            "Como La Flor (Demo)",
            "Como La Flor (Remix)",
            "Como La Flor [Live]",
            "Como La Flor (Versión Acústica)",
        ],
    )
    def test_strips_a_qualifier_parenthetical(self, title: str) -> None:
        assert normalise_title(title) == "como la flor"

    def test_strips_a_slash_joined_group(self) -> None:
        # The real shape in this rotation: "(Live/Remastered 2026)". Both halves
        # are qualifiers, so the group goes.
        assert (
            normalise_title("Si La Quieres (Live/Remastered 2026)") == "si la quieres"
        )

    def test_strips_more_than_one_group(self) -> None:
        assert normalise_title("Como La Flor (Live) (Remastered)") == "como la flor"

    # ------------------------------------------------------------------
    # The half that matters more. CLAUDE.md §9: never strip a parenthetical
    # unless its content matches the stop-list.
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Augen zu (Es regnet Blumen)", "augen zu (es regnet blumen)"),
            ("¿Qué Creías?", "¿qué creías?"),
            ("Marta, Sebas, Guille y los demás", "marta, sebas, guille y los demás"),
            ("(Don't Fear) The Reaper", "(don't fear) the reaper"),
            ("Una Noche (Sin Ti)", "una noche (sin ti)"),
        ],
    )
    def test_keeps_a_parenthetical_that_is_part_of_the_title(
        self, title: str, expected: str
    ) -> None:
        assert normalise_title(title) == expected

    def test_keeps_a_group_where_only_one_half_is_a_qualifier(self) -> None:
        # "Live" alone would go; "Live in Monterrey" is where it was recorded,
        # which is part of what distinguishes this release from another.
        assert (
            normalise_title("Como La Flor (Live in Monterrey)")
            == "como la flor (live in monterrey)"
        )


class TestRule3Featuring:
    @pytest.mark.parametrize(
        "title",
        [
            "Bordbistro feat. Destroy Degenhardt",
            "Bordbistro (feat. Destroy Degenhardt)",
            "Bordbistro [ft. Destroy Degenhardt]",
            "Bordbistro ft Destroy Degenhardt",
            "Bordbistro featuring Destroy Degenhardt",
            "Bordbistro con Destroy Degenhardt",
        ],
    )
    def test_strips_a_featuring_clause(self, title: str) -> None:
        assert normalise_title(title) == "bordbistro"

    def test_con_needs_its_space(self) -> None:
        # Otherwise every title beginning "con" loses its first word.
        assert normalise_title("Contigo") == "contigo"
        assert normalise_title("Conmigo Aprendió") == "conmigo aprendió"
        assert normalise_title("Ven Conmigo") == "ven conmigo"

    def test_keeps_the_primary_artist_only(self) -> None:
        assert (
            normalise_artist("Die Toten Hosen, Blixa Bargeld & Einstürzende Neubauten")
            == "die toten hosen"
        )
        assert normalise_artist("Oidorno feat. Destroy Degenhardt") == "oidorno"
        assert normalise_artist("Bitume & Sterbt Alle") == "bitume"

    def test_does_not_split_an_artist_whose_name_contains_a_marker(self) -> None:
        # `y` splits only when it is a standalone word followed by a space, so
        # a band called "Yo La Tengo" survives.
        assert normalise_artist("Yo La Tengo") == "yo la tengo"


class TestRule4Dashes:
    @pytest.mark.parametrize("dash", ["-", "–", "—", "‑", "‒", "―"])
    def test_normalises_every_dash_variant(self, dash: str) -> None:
        assert normalise_title(f"Como La Flor {dash} Remastered") == "como la flor"

    def test_keeps_a_dash_that_is_not_a_qualifier_separator(self) -> None:
        assert normalise_title("Marta - Sebas") == "marta - sebas"


class TestRule5Whitespace:
    def test_collapses_runs_and_trims(self) -> None:
        assert normalise_title("  Como   La    Flor  ") == "como la flor"


class TestRule6AccentFolding:
    def test_folds_for_the_key_and_keeps_them_in_the_norm(self) -> None:
        result = normalise("¿Qué Creías?", "Selena")
        assert result.title_norm == "¿qué creías?"
        assert result.title_key == "¿que creias?"

    @pytest.mark.parametrize(
        "text,folded",
        [
            ("corazón", "corazon"),
            ("añejo", "anejo"),
            ("público", "publico"),
            ("Jiménez", "Jimenez"),
            ("güero", "guero"),
        ],
    )
    def test_folds_every_spanish_diacritic(self, text: str, folded: str) -> None:
        assert fold_accents(text) == folded

    def test_folding_is_not_applied_to_the_norm(self) -> None:
        # Because `año` and `ano` are different words and only one is a year.
        assert normalise_title("Año Nuevo") == "año nuevo"


class TestNormalisedRecord:
    def test_carries_the_originals_untouched(self) -> None:
        # CLAUDE.md §9: normalisation is for comparison; the original is what
        # gets displayed. It is on the record so nobody has to go looking.
        result = normalise("Como La Flor (Live/Remastered 2026)", "Selena")
        assert result.title == "Como La Flor (Live/Remastered 2026)"
        assert result.artist == "Selena"
        assert result.title_norm == "como la flor"

    def test_key_is_the_cache_key_spec_8_3_asks_for(self) -> None:
        assert normalise("Corazón Espinado", "Santana").key == (
            "santana",
            "corazon espinado",
        )

    def test_two_spellings_of_one_track_produce_one_key(self) -> None:
        # The whole reason the key exists.
        a = normalise("Corazón Espinado (Remastered)", "Santana feat. Maná")
        b = normalise("Corazon Espinado", "Santana")
        assert a.key == b.key


class TestDegenerateInput:
    @pytest.mark.parametrize("value", ["", "   ", "()", "[]", "- Remastered", "&", "-"])
    def test_never_raises(self, value: str) -> None:
        # The contract for junk is "returns a string", not "returns empty".
        # LRCLIB will not match most of these, but the matcher has to reach that
        # conclusion by asking rather than by raising on the way there.
        assert isinstance(normalise_title(value), str)
        assert isinstance(normalise_artist(value), str)

    @pytest.mark.parametrize("value", ["", "   "])
    def test_empty_in_empty_out(self, value: str) -> None:
        assert normalise_title(value) == ""

    def test_a_title_that_is_only_a_qualifier_normalises_to_nothing(self) -> None:
        # This one matters: it is the difference between "no title left to ask
        # about" and "a title that happens to be the word Live".
        assert normalise_title("(Live)") == ""
        assert normalise_title("(Remastered 2026)") == ""

    def test_an_empty_parenthetical_is_kept(self) -> None:
        # Consistent with the rule rather than an oversight: `()` contains
        # nothing, nothing is not on the stop-list, so it is not stripped.
        # CLAUDE.md §9 makes keeping the safe direction, and a title of "()"
        # simply will not match — which is the right outcome for junk.
        assert normalise_title("()") == "()"

    def test_survives_an_artist_that_is_only_a_separator(self) -> None:
        assert normalise_artist("&") == ""
