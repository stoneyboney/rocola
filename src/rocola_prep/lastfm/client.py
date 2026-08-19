"""SPEC §7.1 — the scrobble history, and the selection heuristic over it.

Read-only. There is no write endpoint reachable from this module and no OAuth
flow: last.fm's read methods need only an API key, which is the whole reason
selection can be a background job rather than a login screen.

## Three things this file exists to get right

**The `nowplaying` entry.** `user.getRecentTracks` prepends the track currently
playing, with `@attr.nowplaying = "true"` and **no timestamp**. SPEC §7.1 says
skip it: it reappears as a normal scrobble the moment it finishes, and counting
it means counting one play twice and sorting a `None` date.

**Errors arrive with HTTP 200.** last.fm returns `{"error": 6, "message": "User
not found"}` in a 200 response often enough that a client checking only the
status code reports "no tracks" for a mistyped username. Checked explicitly.

**Pacing.** CLAUDE.md §8: pace requests, do not parallelise aggressively. A
fixed delay between pages, single-threaded. This is somebody's free API and the
job is not urgent.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator

import httpx

from rocola_prep.matcher.normalise import Normalised, normalise

BASE_URL = "https://ws.audioscrobbler.com/2.0/"
USER_AGENT = "rocola/0.1.0 (+https://github.com/stoneyboney/rocola)"

#: What `user.getTopTracks` accepts. `overall` is the whole history.
PERIODS = ("7day", "1month", "3month", "6month", "12month", "overall")


class LastfmError(RuntimeError):
    """last.fm reported a failure — possibly inside a 200 response."""


@dataclass(frozen=True)
class Track:
    """One track from the history, with its normalised forms alongside.

    `title` and `artist` are last.fm's display strings and stay untouched
    (CLAUDE.md §9). `norm` carries the comparison forms.
    """

    title: str
    artist: str
    norm: Normalised
    playcount: int = 0
    mbid: str | None = None
    album: str | None = None
    duration: float | None = None
    last_played_at: datetime | None = None

    @property
    def dedupe_key(self) -> str | tuple[str, str]:
        """SPEC §7.1: by `mbid` when present, else `(artistNorm, titleNorm)`."""
        return self.mbid if self.mbid else self.norm.key


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _float_or_none(value: Any) -> float | None:
    try:
        seconds = float(str(value))
    except (TypeError, ValueError):
        return None
    return seconds if seconds > 0 else None


def _artist_name(raw: Any) -> str:
    """last.fm gives the artist as `{"name": …}` here and `{"#text": …}` there."""
    if isinstance(raw, dict):
        return str(raw.get("name") or raw.get("#text") or "")
    return str(raw or "")


class LastfmClient:
    """Read-only client for the two methods SPEC §7.1 names.

    Takes an injected `httpx.Client` so tests drive it through
    `httpx.MockTransport` and never reach the network.
    """

    def __init__(
        self,
        api_key: str,
        user: str,
        client: httpx.Client | None = None,
        *,
        base_url: str = BASE_URL,
        pace_seconds: float = 0.25,
    ) -> None:
        if not api_key:
            raise LastfmError("no API key: set LASTFM_API_KEY in .env")
        if not user:
            raise LastfmError("no username: set LASTFM_USER in .env")
        self._api_key = api_key
        self._user = user
        self._base_url = base_url
        self._pace = pace_seconds
        self._client = client or httpx.Client(timeout=20.0)
        self._client.headers["User-Agent"] = USER_AGENT

    def _call(self, method: str, **params: Any) -> dict[str, Any]:
        if self._pace:
            time.sleep(self._pace)
        response = self._client.get(
            self._base_url,
            params={
                "method": method,
                "user": self._user,
                "api_key": self._api_key,
                "format": "json",
                **{k: v for k, v in params.items() if v is not None},
            },
        )
        if response.status_code != 200:
            raise LastfmError(f"{method}: HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise LastfmError(f"{method}: response was not JSON") from exc

        # The one that bites: an error inside a 200.
        if isinstance(payload, dict) and "error" in payload:
            raise LastfmError(
                f"{method}: last.fm error {payload.get('error')}: "
                f"{payload.get('message', 'no message')}"
            )
        return payload if isinstance(payload, dict) else {}

    # -- user.getTopTracks -------------------------------------------------

    def top_tracks(self, period: str = "overall", limit: int = 200) -> list[Track]:
        """Most-played tracks over `period`, already deduplicated.

        The natural instrument for "top N by playcount over a window", and one
        request where walking `getRecentTracks` over the same window would be
        dozens.
        """
        if period not in PERIODS:
            raise LastfmError(f"period must be one of {PERIODS}, not {period!r}")

        payload = self._call(
            "user.getTopTracks", period=period, limit=min(limit, 1000)
        )
        raw = payload.get("toptracks", {}).get("track", [])
        if isinstance(raw, dict):
            raw = [raw]

        tracks: list[Track] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            title = str(item.get("name") or "")
            artist = _artist_name(item.get("artist"))
            if not title or not artist:
                continue
            tracks.append(
                Track(
                    title=title,
                    artist=artist,
                    norm=normalise(title, artist),
                    playcount=_int(item.get("playcount")),
                    mbid=str(item.get("mbid")) or None if item.get("mbid") else None,
                    duration=_float_or_none(item.get("duration")),
                )
            )
        return dedupe(tracks)

    # -- user.getRecentTracks ---------------------------------------------

    def recent_tracks(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        page_size: int = 200,
        max_pages: int = 50,
    ) -> list[Track]:
        """Scrobbles in a window, paged, with the `nowplaying` entry skipped.

        SPEC §7.1 walks this back until `lastPlayedAt` falls outside the window.
        Playcount is derived by counting scrobbles of the same track, which is
        what makes the §7.1 threshold ("played >= N times within the window")
        answerable at all.
        """
        counts: dict[str | tuple[str, str], Track] = {}
        plays: dict[str | tuple[str, str], int] = {}

        for scrobble in self._iter_recent(since, until, page_size, max_pages):
            key = scrobble.dedupe_key
            plays[key] = plays.get(key, 0) + 1
            existing = counts.get(key)
            if existing is None or (
                scrobble.last_played_at
                and existing.last_played_at
                and scrobble.last_played_at > existing.last_played_at
            ):
                counts[key] = scrobble

        return sorted(
            (
                Track(
                    title=t.title,
                    artist=t.artist,
                    norm=t.norm,
                    playcount=plays[key],
                    mbid=t.mbid,
                    album=t.album,
                    duration=t.duration,
                    last_played_at=t.last_played_at,
                )
                for key, t in counts.items()
            ),
            key=lambda t: (-t.playcount, t.norm.title_key),
        )

    def _iter_recent(
        self,
        since: datetime | None,
        until: datetime | None,
        page_size: int,
        max_pages: int,
    ) -> Iterator[Track]:
        page = 1
        while page <= max_pages:
            payload = self._call(
                "user.getRecentTracks",
                limit=min(page_size, 200),
                page=page,
                **{
                    "from": int(since.timestamp()) if since else None,
                    "to": int(until.timestamp()) if until else None,
                },
            )
            section = payload.get("recenttracks", {})
            raw = section.get("track", [])
            if isinstance(raw, dict):
                raw = [raw]
            if not raw:
                return

            for item in raw:
                track = self._parse_scrobble(item)
                if track is not None:
                    yield track

            attr = section.get("@attr", {})
            if page >= _int(attr.get("totalPages"), default=page):
                return
            page += 1

    @staticmethod
    def _parse_scrobble(item: Any) -> Track | None:
        if not isinstance(item, dict):
            return None

        # SPEC §7.1: skip the currently-playing entry. It has no `date`, and it
        # will reappear as an ordinary scrobble once it finishes — counting it
        # here counts one play twice.
        attr = item.get("@attr")
        if isinstance(attr, dict) and str(attr.get("nowplaying", "")).lower() == "true":
            return None
        if "date" not in item:
            # Belt and braces: no timestamp means it is the nowplaying entry
            # under a different shape, and it cannot be placed in a window.
            return None

        title = str(item.get("name") or "")
        artist = _artist_name(item.get("artist"))
        if not title or not artist:
            return None

        played_at = None
        date = item.get("date")
        if isinstance(date, dict) and date.get("uts"):
            played_at = datetime.fromtimestamp(_int(date["uts"]), tz=timezone.utc)

        album = item.get("album")
        album_name = (
            str(album.get("#text")) if isinstance(album, dict) and album.get("#text") else None
        )

        return Track(
            title=title,
            artist=artist,
            norm=normalise(title, artist),
            playcount=1,
            mbid=str(item["mbid"]) if item.get("mbid") else None,
            album=album_name,
            last_played_at=played_at,
        )


def dedupe(tracks: list[Track]) -> list[Track]:
    """SPEC §7.1: by `mbid` when present, else `(artistNorm, titleNorm)`.

    Playcounts are summed rather than discarded, because two rows that dedupe
    together are two spellings of one track and the user played it the total
    number of times.
    """
    merged: dict[str | tuple[str, str], Track] = {}
    for track in tracks:
        key = track.dedupe_key
        existing = merged.get(key)
        if existing is None:
            merged[key] = track
            continue
        merged[key] = Track(
            title=existing.title,
            artist=existing.artist,
            norm=existing.norm,
            playcount=existing.playcount + track.playcount,
            mbid=existing.mbid or track.mbid,
            album=existing.album or track.album,
            duration=existing.duration or track.duration,
            last_played_at=max(
                filter(None, [existing.last_played_at, track.last_played_at]),
                default=None,
            ),
        )
    return sorted(merged.values(), key=lambda t: (-t.playcount, t.norm.title_key))
