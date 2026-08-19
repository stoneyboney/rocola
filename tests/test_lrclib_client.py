"""SPEC §8.2's ladder and §8.4's obligations, driven through a mock transport.

No test here touches the network. Every response is hand-written, and the
"lyrics" in them are synthetic Spanish invented for the test — CLAUDE.md §2
forbids a real lyric in a fixture, and these exist to be counted rather than
read anyway.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from rocola_prep.lrclib.client import (
    USER_AGENT,
    Candidate,
    LrclibClient,
    Rung,
    _keep,
)

# Synthetic. Four lines of invented Spanish, written for this file.
SYNTHETIC = "Camino solo por la sierra\nla luna alumbra mi cantar\nel viento lleva mi bandera\ny el cerro me ve pasar"


def record(**overrides: Any) -> dict[str, Any]:
    """An LRCLIB record with every field it really returns, including the two
    lyric-bearing ones that must never survive `_keep`."""
    base = {
        "id": 133901,
        "name": "Camino",
        "trackName": "Camino",
        "artistName": "Ejemplo",
        "albumName": "Disco Inventado",
        "duration": 129.0,
        "instrumental": False,
        "plainLyrics": SYNTHETIC,
        "syncedLyrics": "[00:13.52] Camino solo por la sierra",
        "lyricsfile": "version: '1.0'\nlines:\n- text: Camino solo\n  start_ms: 13520\nplain: |-\n  Camino solo por la sierra",
    }
    base.update(overrides)
    return base


def client_for(handler: Any, **kwargs: Any) -> LrclibClient:
    transport = httpx.MockTransport(handler)
    return LrclibClient(
        httpx.Client(transport=transport), pace_seconds=0.0, **kwargs
    )


class TestTheAllowlist:
    """The reason this module exists in the shape it does."""

    def test_drops_syncedlyrics_and_lyricsfile(self) -> None:
        kept = _keep(record())
        assert kept is not None
        # Not "is None" — the attributes must not exist at all.
        assert not hasattr(kept, "synced_lyrics")
        assert not hasattr(kept, "lyricsfile")
        assert set(vars(kept)) == {
            "id",
            "track_name",
            "artist_name",
            "album_name",
            "duration",
            "instrumental",
            "plain_lyrics",
        }

    def test_keeps_the_plain_text_and_nothing_else_that_is_long(self) -> None:
        kept = _keep(record())
        assert kept is not None
        assert kept.plain_lyrics == SYNTHETIC
        # No other attribute carries anything of lyric length.
        others = [v for k, v in vars(kept).items() if k != "plain_lyrics"]
        assert all(not isinstance(v, str) or len(v) < 60 for v in others)

    def test_a_field_lrclib_has_not_invented_yet_is_dropped(self) -> None:
        # The whole point of allowlisting. A fourth lyric-bearing field added
        # next year is gone by default rather than kept by default.
        kept = _keep(record(lyricsFileV2="...", plainLyricsHtml="<p>...</p>"))
        assert kept is not None
        assert not hasattr(kept, "lyricsFileV2")
        assert not hasattr(kept, "plainLyricsHtml")

    def test_survives_a_response_that_is_not_a_dict(self) -> None:
        # §8.4: treat the API as best-effort. That applies to the shape too.
        assert _keep(None) is None
        assert _keep("nope") is None
        assert _keep([1, 2, 3]) is None


class TestFieldOptionality:
    def test_null_lyrics_stay_none_rather_than_becoming_empty(self) -> None:
        # Measured on a real instrumental: plainLyrics is null, not "".
        kept = _keep(record(plainLyrics=None, syncedLyrics=None, instrumental=True))
        assert kept is not None
        assert kept.plain_lyrics is None
        assert kept.instrumental is True

    def test_whitespace_only_lyrics_count_as_absent(self) -> None:
        kept = _keep(record(plainLyrics="   \n  "))
        assert kept is not None
        assert kept.plain_lyrics is None

    def test_missing_fields_do_not_raise(self) -> None:
        kept = _keep({"id": 1})
        assert kept is not None
        assert kept.album_name is None
        assert kept.duration is None
        assert kept.instrumental is False

    def test_a_non_numeric_duration_is_discarded(self) -> None:
        kept = _keep(record(duration="two minutes"))
        assert kept is not None
        assert kept.duration is None


class TestTheLadder:
    def test_rung_1_when_album_and_duration_are_known(self) -> None:
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            return httpx.Response(200, json=record())

        result = client_for(handler).resolve(
            "Camino", "Ejemplo", album="Disco Inventado", duration=129.0
        )
        assert result.rung is Rung.EXACT_FULL
        assert result.resolved
        assert len(seen) == 1
        assert "album_name=" in seen[0] and "duration=" in seen[0]

    def test_falls_to_rung_2_when_rung_1_finds_nothing(self) -> None:
        calls: list[dict[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(dict(request.url.params))
            if "album_name" in request.url.params:
                return httpx.Response(404, json={"code": 404})
            return httpx.Response(200, json=record())

        result = client_for(handler).resolve(
            "Camino", "Ejemplo", album="Disco Inventado", duration=129.0
        )
        assert result.rung is Rung.EXACT_LOOSE
        assert result.resolved
        assert len(calls) == 2
        assert "album_name" not in calls[1] and "duration" not in calls[1]

    def test_starts_at_rung_2_when_there_is_no_album_or_duration(self) -> None:
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json=record())

        result = client_for(handler).resolve("Camino", "Ejemplo")
        assert result.rung is Rung.EXACT_LOOSE
        assert len(calls) == 1

    def test_rung_3_scores_a_fielded_search(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/get"):
                return httpx.Response(404, json={})
            return httpx.Response(200, json=[record()])

        result = client_for(handler).resolve("Camino", "Ejemplo")
        assert result.rung is Rung.SEARCH_FIELDED
        assert result.resolved
        assert result.score is not None and result.score.score >= 0.85

    def test_rung_4_is_the_freeform_last_resort(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/get"):
                return httpx.Response(404, json={})
            if "q" in request.url.params:
                return httpx.Response(200, json=[record()])
            return httpx.Response(200, json=[])  # fielded search: nothing

        result = client_for(handler).resolve("Camino", "Ejemplo")
        assert result.rung is Rung.SEARCH_FREEFORM
        assert result.resolved

    def test_rung_5_when_nothing_matches(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/get"):
                return httpx.Response(404, json={})
            return httpx.Response(200, json=[])

        result = client_for(handler).resolve("Camino", "Ejemplo")
        assert result.rung is Rung.EXHAUSTED
        assert not result.resolved
        assert result.status == "no_lyrics"

    def test_a_rejected_search_result_does_not_resolve(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/get"):
                return httpx.Response(404, json={})
            return httpx.Response(
                200,
                json=[record(trackName="Algo Completamente Distinto", artistName="Otro")],
            )

        result = client_for(handler).resolve("Camino", "Ejemplo")
        assert result.rung is Rung.EXHAUSTED
        assert not result.resolved


class TestInstrumental:
    def test_is_terminal_and_does_not_fall_through(self) -> None:
        # §8.4: terminal `no_lyrics`, do not retry. Falling through to search
        # would find *something* and attach it to a track with no words.
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(
                200,
                json=record(instrumental=True, plainLyrics=None, syncedLyrics=None),
            )

        result = client_for(handler).resolve("Camino", "Ejemplo")
        assert result.instrumental
        assert result.status == "instrumental"
        assert not result.resolved
        assert len(calls) == 1, "must not have tried a search rung"


class TestReviewBand:
    def test_a_review_scoring_candidate_is_not_resolved(self) -> None:
        # CLAUDE.md §9: never auto-accept 0.70-0.85. It is reported, not used.
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/get"):
                return httpx.Response(404, json={})
            return httpx.Response(
                200,
                json=[record(trackName="Ben Comigo", artistName="Ejemplo y los Otros")],
            )

        result = client_for(handler).resolve("Ven Conmigo", "Ejemplo")
        assert result.needs_review
        assert not result.resolved
        assert result.status == "review"


class TestRequestHygiene:
    def test_sends_the_user_agent_spec_8_4_asks_for(self) -> None:
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers.get("user-agent", ""))
            return httpx.Response(200, json=record())

        client_for(handler).resolve("Camino", "Ejemplo")
        assert seen[0] == USER_AGENT
        assert "rocola" in seen[0]

    def test_a_transport_error_is_a_miss_rather_than_a_crash(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("offline")

        result = client_for(handler).resolve("Camino", "Ejemplo")
        assert result.rung is Rung.EXHAUSTED

    def test_a_body_that_is_not_json_is_a_miss_rather_than_a_crash(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>maintenance</html>")

        result = client_for(handler).resolve("Camino", "Ejemplo")
        assert result.rung is Rung.EXHAUSTED


class TestNothingLeaksSideways:
    def test_the_resolution_carries_no_timed_or_serialised_lyric(self) -> None:
        # The whole object graph, serialised, must contain the plain text and
        # neither of the other two forms.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=record())

        result = client_for(handler).resolve("Camino", "Ejemplo")
        blob = json.dumps(result, default=lambda o: getattr(o, "__dict__", str(o)))
        assert "start_ms" not in blob
        assert "00:13.52" not in blob
        assert "version: '1.0'" not in blob


@pytest.mark.parametrize("status", [404, 500, 429])
def test_a_non_200_on_every_rung_ends_at_exhausted(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={})

    result = client_for(handler).resolve("Camino", "Ejemplo")
    assert result.rung is Rung.EXHAUSTED
    assert isinstance(result.candidate, type(None))


def test_candidate_is_frozen() -> None:
    kept = _keep(record())
    assert isinstance(kept, Candidate)
    with pytest.raises(Exception):
        kept.plain_lyrics = "mutated"  # type: ignore[misc]
