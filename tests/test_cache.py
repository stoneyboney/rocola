"""SPEC §8.3 — hits and misses both cached, misses re-checked monthly.

The load-bearing test in here is the last class: the cache must be incapable of
holding lyric text, not merely uninterested in it.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from rocola_prep.lrclib.cache import MISS_TTL, ResolutionCache
from rocola_prep.lrclib.client import Candidate, Resolution, Rung
from rocola_prep.matcher.normalise import normalise

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)

SYNTHETIC = "Camino solo por la sierra\nla luna alumbra mi cantar"


def resolution(
    title: str = "Camino",
    artist: str = "Ejemplo",
    *,
    rung: Rung = Rung.EXACT_LOOSE,
    lyrics: str | None = SYNTHETIC,
    instrumental: bool = False,
    needs_review: bool = False,
    lrclib_id: int | None = 133901,
) -> Resolution:
    candidate = (
        None
        if lrclib_id is None
        else Candidate(
            id=lrclib_id,
            track_name=title,
            artist_name=artist,
            album_name=None,
            duration=None,
            instrumental=instrumental,
            plain_lyrics=lyrics,
        )
    )
    return Resolution(
        query=normalise(title, artist),
        rung=rung,
        candidate=candidate,
        instrumental=instrumental,
        needs_review=needs_review,
    )


@pytest.fixture
def cache(tmp_path: Path) -> ResolutionCache:
    with ResolutionCache(tmp_path / "lrclib.sqlite3") as c:
        yield c


class TestHitsAndMisses:
    def test_a_hit_is_remembered(self, cache: ResolutionCache) -> None:
        r = resolution()
        cache.put(r, now=NOW)
        found = cache.get(r.query.key, now=NOW)
        assert found is not None
        assert found.status == "resolved"
        assert found.lrclib_id == 133901
        assert found.rung is Rung.EXACT_LOOSE

    def test_a_miss_is_remembered_too(self, cache: ResolutionCache) -> None:
        # §8.3's actual point. A miss costs the whole four-rung ladder to
        # rediscover, and a rotation is mostly the same tracks every week.
        r = resolution(rung=Rung.EXHAUSTED, lyrics=None, lrclib_id=None)
        cache.put(r, now=NOW)
        found = cache.get(r.query.key, now=NOW)
        assert found is not None
        assert found.status == "no_lyrics"
        assert found.is_miss

    def test_an_unknown_key_is_none(self, cache: ResolutionCache) -> None:
        assert cache.get(("nadie", "nada"), now=NOW) is None

    def test_the_key_is_the_normalised_pair_spec_8_3_specifies(
        self, cache: ResolutionCache
    ) -> None:
        cache.put(resolution("Camino", "Ejemplo"), now=NOW)
        # A differently-spelled scrobble of the same track hits the same row.
        other = normalise("Camino (Remastered)", "Ejemplo feat. Alguien")
        assert cache.get(other.key, now=NOW) is not None

    def test_writing_twice_updates_rather_than_duplicates(
        self, cache: ResolutionCache
    ) -> None:
        cache.put(resolution(rung=Rung.EXHAUSTED, lyrics=None), now=NOW)
        cache.put(resolution(rung=Rung.EXACT_FULL), now=NOW)
        found = cache.get(normalise("Camino", "Ejemplo").key, now=NOW)
        assert found is not None
        assert found.rung is Rung.EXACT_FULL
        assert found.status == "resolved"


class TestMonthlyRecheck:
    def test_a_fresh_miss_is_served_from_cache(self, cache: ResolutionCache) -> None:
        r = resolution(rung=Rung.EXHAUSTED, lyrics=None, lrclib_id=None)
        cache.put(r, now=NOW)
        assert cache.get(r.query.key, now=NOW + timedelta(days=29)) is not None

    def test_a_stale_miss_is_treated_as_unknown(self, cache: ResolutionCache) -> None:
        # §8.3: LRCLIB is crowdsourced and grows. A track with no lyrics today
        # may have them in six weeks, and a permanent miss is a decision made
        # once in ignorance and never revisited.
        r = resolution(rung=Rung.EXHAUSTED, lyrics=None, lrclib_id=None)
        cache.put(r, now=NOW)
        assert cache.get(r.query.key, now=NOW + MISS_TTL) is None
        assert cache.get(r.query.key, now=NOW + timedelta(days=60)) is None

    def test_a_hit_never_goes_stale(self, cache: ResolutionCache) -> None:
        r = resolution()
        cache.put(r, now=NOW)
        assert cache.get(r.query.key, now=NOW + timedelta(days=3650)) is not None

    def test_an_instrumental_never_goes_stale(self, cache: ResolutionCache) -> None:
        # §8.4 calls it terminal. Re-checking asks a question whose answer
        # cannot change: the recording has no words in it.
        r = resolution(instrumental=True, lyrics=None)
        cache.put(r, now=NOW)
        found = cache.get(r.query.key, now=NOW + timedelta(days=3650))
        assert found is not None
        assert found.status == "instrumental"

    def test_a_review_band_result_is_rechecked_like_a_miss(
        self, cache: ResolutionCache
    ) -> None:
        # It is not a match, so it should not be remembered as one forever —
        # a better candidate may be uploaded.
        r = resolution(rung=Rung.SEARCH_FIELDED, needs_review=True)
        cache.put(r, now=NOW)
        assert cache.get(r.query.key, now=NOW).is_miss  # type: ignore[union-attr]
        assert cache.get(r.query.key, now=NOW + MISS_TTL) is None


class TestTheCacheCannotHoldLyrics:
    """CLAUDE.md §2, enforced by schema rather than by discipline.

    `cache/` is gitignored, but gitignored is one `git add -f` from untrue. The
    rule worth having is the one that cannot be undone by a flag: there is no
    column here that lyric text could go in.
    """

    def test_the_schema_has_no_column_for_text(self, cache: ResolutionCache) -> None:
        assert set(cache.columns()) == {
            "artist_key",
            "title_key",
            "status",
            "rung",
            "lrclib_id",
            "checked_at",
        }

    def test_storing_a_resolution_writes_none_of_its_lyrics(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "lrclib.sqlite3"
        with ResolutionCache(path) as c:
            c.put(resolution(), now=NOW)

        # Read the file as bytes. Not "check the columns" — check the artefact.
        blob = path.read_bytes()
        assert SYNTHETIC.encode() not in blob
        assert b"Camino solo por la sierra" not in blob
        assert b"la luna alumbra" not in blob

    def test_every_stored_value_is_short(self, cache: ResolutionCache) -> None:
        cache.put(resolution(), now=NOW)
        rows = cache._db.execute("SELECT * FROM resolutions").fetchall()  # noqa: SLF001
        for row in rows:
            for value in row:
                assert not isinstance(value, str) or len(value) < 64

    def test_survives_a_reopen(self, tmp_path: Path) -> None:
        path = tmp_path / "lrclib.sqlite3"
        with ResolutionCache(path) as c:
            c.put(resolution(), now=NOW)
        with ResolutionCache(path) as c:
            assert c.get(normalise("Camino", "Ejemplo").key, now=NOW) is not None

    def test_creates_its_parent_directory(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "deeper" / "lrclib.sqlite3"
        with ResolutionCache(path) as c:
            c.put(resolution(), now=NOW)
        assert path.exists()
        assert isinstance(sqlite3.connect(path), sqlite3.Connection)
