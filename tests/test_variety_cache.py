"""The variety store and the pass over it. Nothing here reaches Ollama."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from molcajete_prep.glossing.provider import GlossTask

from rocola_prep.variety.cache import VarietyCache
from rocola_prep.variety.models import Register, Variety, VarietySense
from rocola_prep.variety.prompts import PROMPT_VERSION
from rocola_prep.variety.tagger import tag

PIBE = VarietySense(
    lemma="pibe",
    pos="NOUN",
    de="der Junge",
    en="kid",
    variety=Variety.AR,
    register=Register.COLOQUIAL,
    home_equivalent="chavo",
    home_equivalent_note="In Mexiko sagt man 'chavo'.",
    confidence=0.9,
)


def cache_at(path: Path, **overrides) -> VarietyCache:
    options = {
        "model": "gemma3:12b",
        "prompt_version": PROMPT_VERSION,
        "home_dialect": Variety.MX,
    }
    options.update(overrides)
    return VarietyCache(path / "variety.sqlite3", **options)


class TestRoundTrip:
    def test_a_sense_survives_storage(self, tmp_path: Path) -> None:
        with cache_at(tmp_path) as cache:
            cache.put(PIBE)
            found = cache.get(("pibe", "NOUN"))

        assert found is not None
        assert found.de == "der Junge"
        assert found.variety is Variety.AR
        assert found.register is Register.COLOQUIAL
        assert found.home_equivalent == "chavo"
        assert found.confidence == 0.9

    def test_an_unknown_lemma_is_none(self, tmp_path: Path) -> None:
        with cache_at(tmp_path) as cache:
            assert cache.get(("nadie", "NOUN")) is None

    def test_survives_a_reopen(self, tmp_path: Path) -> None:
        with cache_at(tmp_path) as cache:
            cache.put(PIBE)
        with cache_at(tmp_path) as cache:
            assert cache.get(("pibe", "NOUN")) is not None

    def test_writing_twice_updates_rather_than_duplicates(self, tmp_path: Path) -> None:
        with cache_at(tmp_path) as cache:
            cache.put(PIBE)
            cache.put(VarietySense(lemma="pibe", pos="NOUN", de="der Kerl"))
            assert cache.count() == 1
            found = cache.get(("pibe", "NOUN"))
            assert found is not None and found.de == "der Kerl"

    def test_get_many_returns_only_hits(self, tmp_path: Path) -> None:
        with cache_at(tmp_path) as cache:
            cache.put(PIBE)
            found = cache.get_many([("pibe", "NOUN"), ("nadie", "NOUN")])
            assert set(found) == {("pibe", "NOUN")}


class TestTheKey:
    """Five parts, and the interesting one is the last."""

    def test_pos_separates_two_senses_of_one_string(self, tmp_path: Path) -> None:
        with cache_at(tmp_path) as cache:
            cache.put(VarietySense(lemma="bajo", pos="NOUN", de="der Bass"))
            cache.put(VarietySense(lemma="bajo", pos="ADP", de="unter"))
            assert cache.get(("bajo", "NOUN")).de == "der Bass"  # type: ignore[union-attr]
            assert cache.get(("bajo", "ADP")).de == "unter"  # type: ignore[union-attr]

    def test_a_different_model_does_not_answer_for_this_one(self, tmp_path: Path) -> None:
        # A 12B answer and a frontier answer are different claims about one word.
        with cache_at(tmp_path, model="gemma3:12b") as cache:
            cache.put(PIBE)
        with cache_at(tmp_path, model="llama3:70b") as cache:
            assert cache.get(("pibe", "NOUN")) is None

    def test_a_prompt_change_invalidates(self, tmp_path: Path) -> None:
        with cache_at(tmp_path, prompt_version=1) as cache:
            cache.put(PIBE)
        with cache_at(tmp_path, prompt_version=2) as cache:
            assert cache.get(("pibe", "NOUN")) is None

    def test_the_home_dialect_is_in_the_key(self, tmp_path: Path) -> None:
        # SPEC §15 q4: homeEquivalent is generated against one home dialect, so
        # switching requires a re-gloss. In the key, that is a cache miss
        # rather than a caveat — and a miss is the failure you notice.
        with cache_at(tmp_path, home_dialect=Variety.MX) as cache:
            cache.put(PIBE)
            assert cache.get(("pibe", "NOUN")) is not None
        with cache_at(tmp_path, home_dialect=Variety.AR) as cache:
            assert cache.get(("pibe", "NOUN")) is None

    def test_and_the_mexican_answer_is_still_there_afterwards(
        self, tmp_path: Path
    ) -> None:
        # Moving home and moving back should not have cost anything.
        with cache_at(tmp_path, home_dialect=Variety.MX) as cache:
            cache.put(PIBE)
        with cache_at(tmp_path, home_dialect=Variety.AR) as cache:
            cache.put(VarietySense(lemma="pibe", pos="NOUN", variety=Variety.AR))
        with cache_at(tmp_path, home_dialect=Variety.MX) as cache:
            found = cache.get(("pibe", "NOUN"))
            assert found is not None and found.home_equivalent == "chavo"


class TestNoLyricsInHere:
    def test_the_schema_has_no_column_for_a_line(self, tmp_path: Path) -> None:
        # A row is a lemma, a two-word gloss and a label. The example line that
        # justified the gloss is deliberately not stored: a line of a song is a
        # line of a song wherever it is written down.
        with cache_at(tmp_path) as cache:
            assert "example" not in " ".join(cache.columns())
            assert "line" not in " ".join(cache.columns())
            assert "lyric" not in " ".join(cache.columns())

    def test_nothing_long_is_written(self, tmp_path: Path) -> None:
        with cache_at(tmp_path) as cache:
            cache.put(PIBE)
            rows = cache._db.execute("SELECT * FROM senses").fetchall()  # noqa: SLF001
            for row in rows:
                for value in row:
                    assert not isinstance(value, str) or len(value) < 120


class TestTheTagger:
    """Driven through the provider's `transport` seam, as its own tests are."""

    def reply(self, **overrides):
        sense = {
            "lemma": "pibe",
            "pos": "NOUN",
            "glossDe": "der Junge",
            "glossEn": "kid",
            "variety": "es-AR",
            "register": "coloquial",
            "homeEquivalent": "chavo",
            "homeEquivalentNote": "In Mexiko sagt man 'chavo'.",
            "morphNote": None,
            "notSpanish": False,
            "confidence": 0.9,
        }
        sense.update(overrides)

        def transport(url, payload, timeout):
            return {"message": {"content": json.dumps({"glosses": [sense]})}}

        return transport

    def test_tags_a_lemma_through_the_shared_provider(self, tmp_path: Path) -> None:
        result = tag(
            [GlossTask(lemma="pibe", pos="NOUN")],
            home_dialect=Variety.MX,
            cache_path=tmp_path / "v.sqlite3",
            transport=self.reply(),
        )
        assert result.from_model == 1
        assert result.from_cache == 0
        sense = result.senses[("pibe", "NOUN")]
        assert sense.variety is Variety.AR
        assert sense.home_equivalent == "chavo"

    def test_the_second_run_is_served_from_cache(self, tmp_path: Path) -> None:
        calls: list[int] = []

        def counting(url, payload, timeout):
            calls.append(1)
            return self.reply()(url, payload, timeout)

        path = tmp_path / "v.sqlite3"
        task = [GlossTask(lemma="pibe", pos="NOUN")]
        tag(task, cache_path=path, transport=counting)
        second = tag(task, cache_path=path, transport=counting)

        assert len(calls) == 1, "the model must not have been asked twice"
        assert second.from_cache == 1
        assert second.from_model == 0

    def test_a_run_without_a_cache_asks_every_time(self, tmp_path: Path) -> None:
        # What the eval does: it is measuring the model, and a warm cache would
        # measure the previous run instead.
        calls: list[int] = []

        def counting(url, payload, timeout):
            calls.append(1)
            return self.reply()(url, payload, timeout)

        task = [GlossTask(lemma="pibe", pos="NOUN")]
        tag(task, transport=counting)
        tag(task, transport=counting)
        assert len(calls) == 2

    def test_regional_filters_to_the_tagged_ones(self, tmp_path: Path) -> None:
        general = tag(
            [GlossTask(lemma="pibe", pos="NOUN")],
            transport=self.reply(variety="general", homeEquivalent=None),
        )
        assert general.regional == {}

        regional = tag(
            [GlossTask(lemma="pibe", pos="NOUN")], transport=self.reply()
        )
        assert set(regional.regional) == {("pibe", "NOUN")}

    def test_a_home_dialect_answer_loses_its_equivalent_end_to_end(
        self, tmp_path: Path
    ) -> None:
        # The normalisation is not just unit-tested; it survives the round trip
        # through the provider and into the store.
        path = tmp_path / "v.sqlite3"
        tag(
            [GlossTask(lemma="pibe", pos="NOUN")],
            home_dialect=Variety.MX,
            cache_path=path,
            transport=self.reply(variety="es-MX", homeEquivalent="morro"),
        )
        stored = VarietyCache(
            path,
            model="gemma3:12b",
            prompt_version=PROMPT_VERSION,
            home_dialect=Variety.MX,
        )
        found = stored.get(("pibe", "NOUN"))
        stored.close()
        assert found is not None
        assert found.variety is Variety.MX
        assert found.home_equivalent is None
