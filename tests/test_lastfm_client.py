"""SPEC §7.1's selection input, and the three things it is easy to get wrong.

No test reaches the network; every response is hand-written and driven through
`httpx.MockTransport`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from rocola_prep.config import describe, load_env
from rocola_prep.lastfm.client import LastfmClient, LastfmError, Track, dedupe
from rocola_prep.matcher.normalise import normalise


def client_for(handler: Any) -> LastfmClient:
    return LastfmClient(
        "key", "stoneyboney", httpx.Client(transport=httpx.MockTransport(handler)),
        pace_seconds=0.0,
    )


def top_payload(*tracks: dict[str, Any]) -> dict[str, Any]:
    return {"toptracks": {"track": list(tracks)}}


def top_track(name: str, artist: str, playcount: int = 1, **extra: Any) -> dict[str, Any]:
    return {
        "name": name,
        "artist": {"name": artist},
        "playcount": str(playcount),
        **extra,
    }


def scrobble(name: str, artist: str, uts: int, **extra: Any) -> dict[str, Any]:
    return {
        "name": name,
        "artist": {"#text": artist},
        "date": {"uts": str(uts)},
        **extra,
    }


class TestTopTracks:
    def test_parses_the_shape_lastfm_returns(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json=top_payload(top_track("Como La Flor", "Selena", 47))
            )

        tracks = client_for(handler).top_tracks("overall", 10)
        assert len(tracks) == 1
        assert tracks[0].title == "Como La Flor"
        assert tracks[0].artist == "Selena"
        assert tracks[0].playcount == 47
        assert tracks[0].norm.title_key == "como la flor"

    def test_a_single_track_comes_back_as_a_dict_not_a_list(self) -> None:
        # last.fm collapses a one-element list into the object itself.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"toptracks": {"track": top_track("Solo", "Uno", 3)}}
            )

        assert len(client_for(handler).top_tracks()) == 1

    def test_sorts_by_playcount_descending(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=top_payload(
                    top_track("Poco", "A", 2),
                    top_track("Mucho", "B", 90),
                    top_track("Medio", "C", 20),
                ),
            )

        counts = [t.playcount for t in client_for(handler).top_tracks()]
        assert counts == [90, 20, 2]

    def test_rejects_an_unknown_period_before_calling(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            raise AssertionError("must not have been called")

        with pytest.raises(LastfmError, match="period"):
            client_for(handler).top_tracks("90day")

    def test_skips_rows_missing_a_title_or_artist(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=top_payload(
                    top_track("Bien", "Artista", 5),
                    {"name": "", "artist": {"name": "Nadie"}},
                    {"artist": {"name": "Sin Titulo"}},
                    "not even a dict",
                ),
            )

        assert [t.title for t in client_for(handler).top_tracks()] == ["Bien"]


class TestTopTrackPaging:
    def test_reads_one_page_by_default(self) -> None:
        pages: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            pages.append(int(request.url.params.get("page", 1)))
            return httpx.Response(
                200,
                json={
                    "toptracks": {
                        "track": [top_track("Una", "Artista", 5)],
                        "@attr": {"totalPages": "9"},
                    }
                },
            )

        client_for(handler).top_tracks()
        assert pages == [1]

    def test_walks_further_when_asked(self) -> None:
        # The gap this closes: a history dominated by one artist pushes
        # everything else past page 1, and a client reading only page 1 reports
        # that the rest of the library does not exist.
        pages: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            page = int(request.url.params.get("page", 1))
            pages.append(page)
            return httpx.Response(
                200,
                json={
                    "toptracks": {
                        "track": [top_track(f"Track {page}", "Artista", 10 - page)],
                        "@attr": {"totalPages": "3"},
                    }
                },
            )

        tracks = client_for(handler).top_tracks(max_pages=5)
        assert pages == [1, 2, 3], "must stop at totalPages, not at max_pages"
        assert len(tracks) == 3

    def test_stops_at_max_pages_even_when_more_exist(self) -> None:
        pages: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            page = int(request.url.params.get("page", 1))
            pages.append(page)
            return httpx.Response(
                200,
                json={
                    "toptracks": {
                        "track": [top_track(f"Track {page}", "Artista", 1)],
                        "@attr": {"totalPages": "100"},
                    }
                },
            )

        client_for(handler).top_tracks(max_pages=2)
        assert pages == [1, 2]

    def test_an_empty_page_ends_the_walk(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            page = int(request.url.params.get("page", 1))
            tracks = [top_track("Una", "Artista", 5)] if page == 1 else []
            return httpx.Response(
                200,
                json={"toptracks": {"track": tracks, "@attr": {"totalPages": "50"}}},
            )

        assert len(client_for(handler).top_tracks(max_pages=10)) == 1


class TestErrorInsideA200:
    def test_an_error_body_with_status_200_raises(self) -> None:
        # The failure this client exists to notice. Without the check, a
        # mistyped username reports "no tracks" and the probe measures nothing.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"error": 6, "message": "User not found"})

        with pytest.raises(LastfmError, match="User not found"):
            client_for(handler).top_tracks()

    def test_an_invalid_key_is_reported_with_its_code(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"error": 10, "message": "Invalid API key"})

        with pytest.raises(LastfmError, match="10"):
            client_for(handler).top_tracks()

    def test_a_real_http_error_still_raises(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="down")

        with pytest.raises(LastfmError, match="503"):
            client_for(handler).top_tracks()

    def test_a_non_json_body_raises_rather_than_returning_nothing(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>maintenance</html>")

        with pytest.raises(LastfmError, match="not JSON"):
            client_for(handler).top_tracks()


class TestNowPlaying:
    def test_the_nowplaying_entry_is_skipped(self) -> None:
        # SPEC §7.1: no timestamp, and it reappears as an ordinary scrobble
        # once it finishes. Counting it counts one play twice.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "recenttracks": {
                        "track": [
                            {
                                "name": "Sonando Ahora",
                                "artist": {"#text": "Alguien"},
                                "@attr": {"nowplaying": "true"},
                            },
                            scrobble("Terminada", "Alguien", 1755600000),
                        ],
                        "@attr": {"totalPages": "1"},
                    }
                },
            )

        tracks = client_for(handler).recent_tracks()
        assert [t.title for t in tracks] == ["Terminada"]

    def test_an_entry_without_a_date_is_skipped_however_it_is_marked(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "recenttracks": {
                        "track": [
                            {"name": "Sin Fecha", "artist": {"#text": "Alguien"}},
                            scrobble("Con Fecha", "Alguien", 1755600000),
                        ],
                        "@attr": {"totalPages": "1"},
                    }
                },
            )

        assert [t.title for t in client_for(handler).recent_tracks()] == ["Con Fecha"]

    def test_counts_repeats_as_playcount(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "recenttracks": {
                        "track": [
                            scrobble("Repetida", "Alguien", 1755600000),
                            scrobble("Repetida", "Alguien", 1755603600),
                            scrobble("Repetida", "Alguien", 1755607200),
                            scrobble("Una Vez", "Otro", 1755610800),
                        ],
                        "@attr": {"totalPages": "1"},
                    }
                },
            )

        tracks = client_for(handler).recent_tracks()
        assert tracks[0].title == "Repetida"
        assert tracks[0].playcount == 3
        assert tracks[0].last_played_at == datetime(
            2025, 8, 19, 12, 40, tzinfo=timezone.utc
        )

    def test_walks_pages_until_the_last_one(self) -> None:
        pages: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            page = int(request.url.params.get("page", 1))
            pages.append(page)
            return httpx.Response(
                200,
                json={
                    "recenttracks": {
                        "track": [scrobble(f"Track {page}", "Alguien", 1755600000 + page)],
                        "@attr": {"totalPages": "3"},
                    }
                },
            )

        tracks = client_for(handler).recent_tracks()
        assert pages == [1, 2, 3]
        assert len(tracks) == 3


class TestDedupe:
    def test_by_mbid_when_present(self) -> None:
        # Two spellings, one mbid: one track, and the playcounts add up.
        a = Track("Como La Flor", "Selena", normalise("Como La Flor", "Selena"), 10, mbid="abc")
        b = Track("Como la flor", "SELENA", normalise("Como la flor", "SELENA"), 5, mbid="abc")
        merged = dedupe([a, b])
        assert len(merged) == 1
        assert merged[0].playcount == 15

    def test_by_normalised_pair_when_there_is_no_mbid(self) -> None:
        a = Track(
            "Corazón Espinado (Remastered)",
            "Santana feat. Maná",
            normalise("Corazón Espinado (Remastered)", "Santana feat. Maná"),
            4,
        )
        b = Track(
            "Corazon Espinado", "Santana", normalise("Corazon Espinado", "Santana"), 6
        )
        merged = dedupe([a, b])
        assert len(merged) == 1
        assert merged[0].playcount == 10

    def test_keeps_genuinely_different_tracks_apart(self) -> None:
        a = Track("Como La Flor", "Selena", normalise("Como La Flor", "Selena"), 4)
        b = Track("Amor Prohibido", "Selena", normalise("Amor Prohibido", "Selena"), 6)
        assert len(dedupe([a, b])) == 2

    def test_different_mbids_are_different_tracks(self) -> None:
        a = Track("Igual", "Mismo", normalise("Igual", "Mismo"), 1, mbid="one")
        b = Track("Igual", "Mismo", normalise("Igual", "Mismo"), 1, mbid="two")
        assert len(dedupe([a, b])) == 2


class TestConstruction:
    def test_refuses_to_be_built_without_a_key(self) -> None:
        with pytest.raises(LastfmError, match="LASTFM_API_KEY"):
            LastfmClient("", "someone")

    def test_refuses_to_be_built_without_a_user(self) -> None:
        with pytest.raises(LastfmError, match="LASTFM_USER"):
            LastfmClient("key", "")


class TestEnvLoading:
    def test_parses_the_shapes_a_dotenv_actually_contains(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text(
            "# a comment\n"
            "\n"
            "LASTFM_API_KEY=abc123\n"
            'LASTFM_USER="stoneyboney"\n'
            "export QUOTED='single'\n"
            "  SPACED  =  value  \n"
            "malformed line without equals\n"
        )
        values = load_env(env, overlay_os=False)
        assert values["LASTFM_API_KEY"] == "abc123"
        assert values["LASTFM_USER"] == "stoneyboney"
        assert values["QUOTED"] == "single"
        assert values["SPACED"] == "value"
        assert "malformed line without equals" not in values

    def test_a_missing_file_is_empty_rather_than_an_error(self, tmp_path: Path) -> None:
        assert load_env(tmp_path / "nope.env", overlay_os=False) == {}

    def test_the_environment_overlays_the_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env = tmp_path / ".env"
        env.write_text("LASTFM_API_KEY=from-file\n")
        monkeypatch.setenv("LASTFM_API_KEY", "from-env")
        assert load_env(env)["LASTFM_API_KEY"] == "from-env"

    def test_describe_never_returns_the_value(self) -> None:
        # So that a probe can report its configuration without a credential
        # landing in a terminal buffer or a screenshot.
        values = {"LASTFM_API_KEY": "a-real-looking-secret"}
        assert describe(values, "LASTFM_API_KEY") == "set"
        assert describe(values, "LASTFM_USER") == "missing"
        assert "secret" not in describe(values, "LASTFM_API_KEY")
