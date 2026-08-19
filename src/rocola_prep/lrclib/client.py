"""SPEC §8.2's lookup ladder, and §8.4's obligations to LRCLIB.

## The allowlist is the first thing in this file for a reason

LRCLIB returns **three** fields carrying lyric text:

    plainLyrics    the plain text            <- the only one we want
    syncedLyrics   LRC, with timestamps
    lyricsfile     YAML: the timed lines AND a second full copy of the plain

CLAUDE.md §1 forbids keeping timed lyrics and §2 forbids letting lyric text
settle anywhere it could be committed. `lyricsfile` is named in neither SPEC
§7.2 nor the original §1 — it was found by looking at a live response — and a
client written to "discard syncedLyrics" keeps both the timestamps and the text
inside it.

So `_keep` runs on the raw decoded JSON and **allowlists**. Anything LRCLIB adds
later is dropped by default rather than kept by default, which is the only
arrangement that survives a field nobody has read the release notes for.

## The rung is a return value, not a log line

SPEC §14's Phase 1 asks which rung resolved each track, because that is what
says whether the fuzzy layer is earning its complexity or whether normalisation
is the bottleneck. A rung recorded only in a log is a rung you cannot count, so
`Resolution.rung` is part of the type.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

import httpx

from rocola_prep.matcher.normalise import Normalised, normalise
from rocola_prep.matcher.score import Scored, Verdict, score_candidate

BASE_URL = "https://lrclib.net/api"

#: §8.4 asks for a User-Agent naming the application and version. It costs
#: nothing and it is asked for.
USER_AGENT = "rocola/0.1.0 (+https://github.com/stoneyboney/rocola)"

#: Everything else is dropped. See the module docstring.
_ALLOWED_FIELDS = frozenset(
    {"id", "trackName", "artistName", "albumName", "duration", "instrumental"}
)
_LYRIC_FIELD = "plainLyrics"


class Rung(IntEnum):
    """Which step of §8.2's ladder produced the answer."""

    EXACT_FULL = 1
    """`/api/get` with album and duration. Highest precision."""
    EXACT_LOOSE = 2
    """`/api/get` without album or duration — most scrobbles lack both."""
    SEARCH_FIELDED = 3
    """`/api/search?track_name=&artist_name=`, scored."""
    SEARCH_FREEFORM = 4
    """`/api/search?q=`, scored. Last resort."""
    EXHAUSTED = 5
    """Nothing matched. SPEC §6.1's `no_lyrics`."""

    CACHED = 0
    """Answered from the §8.3 cache without asking LRCLIB."""


@dataclass(frozen=True)
class Candidate:
    """One LRCLIB record, with every lyric-bearing field already gone but one."""

    id: int | None
    track_name: str
    artist_name: str
    album_name: str | None
    duration: float | None
    instrumental: bool
    #: Held only long enough to be measured and classified. Never persisted,
    #: never logged, never returned to anything that writes to disk.
    plain_lyrics: str | None


@dataclass(frozen=True)
class Resolution:
    """What the ladder concluded, and where it got to."""

    query: Normalised
    rung: Rung
    candidate: Candidate | None
    #: Present when a search rung scored something, whether or not it accepted.
    score: Scored | None = None
    #: True when §8.4's terminal instrumental case fired. Never retried.
    instrumental: bool = False
    #: True when the best candidate landed in §8.2's 0.70-0.85 band. Not a
    #: match: CLAUDE.md §9 forbids auto-accepting one.
    needs_review: bool = False

    @property
    def resolved(self) -> bool:
        """A usable lyric was found.

        Deliberately false for the review band and for instrumentals. Checking
        only "is there a candidate with text on it" would report a 0.70-0.85
        match as usable, which is the precise thing CLAUDE.md §9 forbids — and
        it would do so silently, since the candidate does carry lyrics. They are
        just possibly the wrong ones.
        """
        if self.needs_review or self.instrumental:
            return False
        return self.candidate is not None and self.candidate.plain_lyrics is not None

    @property
    def status(self) -> str:
        if self.instrumental:
            return "instrumental"
        if self.resolved:
            return "resolved"
        if self.needs_review:
            return "review"
        return "no_lyrics"


def _keep(raw: Any) -> Candidate | None:
    """Allowlist the fields of one raw LRCLIB record.

    Returns `None` for anything that is not a dict, because §8.4 says to treat
    the API as best-effort and never assume a field is present — which applies
    to the shape of the response as much as to its contents.
    """
    if not isinstance(raw, dict):
        return None

    kept = {k: v for k, v in raw.items() if k in _ALLOWED_FIELDS}
    lyrics = raw.get(_LYRIC_FIELD)

    # `None`, not `""`. An instrumental record returns null for every lyric
    # field, and `or ""` here would turn "absent" into "empty" and lose the
    # distinction the ladder needs.
    if lyrics is not None and not isinstance(lyrics, str):
        lyrics = None
    if isinstance(lyrics, str) and not lyrics.strip():
        lyrics = None

    duration = kept.get("duration")
    if duration is not None and not isinstance(duration, (int, float)):
        duration = None

    return Candidate(
        id=kept.get("id") if isinstance(kept.get("id"), int) else None,
        track_name=str(kept.get("trackName") or ""),
        artist_name=str(kept.get("artistName") or ""),
        album_name=str(kept["albumName"]) if kept.get("albumName") else None,
        duration=float(duration) if duration is not None else None,
        instrumental=bool(kept.get("instrumental", False)),
        plain_lyrics=lyrics,
    )


class LrclibClient:
    """§8.2's ladder over `lrclib.net`.

    Takes an injected `httpx.Client` so that tests drive it through
    `httpx.MockTransport` and never reach the network.
    """

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        base_url: str = BASE_URL,
        pace_seconds: float = 0.2,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._pace = pace_seconds
        self._client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=15.0
        )
        # Assigned, not `setdefault`. httpx presets `user-agent` to
        # `python-httpx/x.y.z` on every client it constructs, so a setdefault
        # here never fires and §8.4's header never gets sent — which is exactly
        # what happened, and what the test now pins.
        self._client.headers["User-Agent"] = USER_AGENT

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        """One paced request. Returns `None` on any non-200 or unparseable body."""
        if self._pace:
            time.sleep(self._pace)
        try:
            response = self._client.get(f"{self._base_url}{path}", params=params)
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    # -- the rungs ---------------------------------------------------------

    def _exact(self, query: Normalised, *, loose: bool, **extra: Any) -> Candidate | None:
        params: dict[str, Any] = {
            "track_name": query.title_norm,
            "artist_name": query.artist_norm,
        }
        if not loose:
            params.update({k: v for k, v in extra.items() if v is not None})
        return _keep(self._get("/get", params))

    def _search(self, params: dict[str, Any]) -> list[Candidate]:
        raw = self._get("/search", params)
        if not isinstance(raw, list):
            return []
        return [c for c in (_keep(r) for r in raw) if c is not None]

    def _best(
        self, query: Normalised, candidates: list[Candidate], duration: float | None
    ) -> tuple[Candidate, Scored] | None:
        scored: list[tuple[Candidate, Scored]] = []
        for candidate in candidates:
            other = normalise(candidate.track_name, candidate.artist_name)
            result = score_candidate(
                title_key=query.title_key,
                artist_key=query.artist_key,
                candidate_title_key=other.title_key,
                candidate_artist_key=other.artist_key,
                scrobbled_duration=duration,
                candidate_duration=candidate.duration,
            )
            scored.append((candidate, result))
        if not scored:
            return None
        return max(scored, key=lambda pair: pair[1].score)

    # -- the ladder --------------------------------------------------------

    def resolve(
        self,
        title: str,
        artist: str,
        *,
        album: str | None = None,
        duration: float | None = None,
    ) -> Resolution:
        """Walk §8.2's five rungs and report where it stopped."""
        query = normalise(title, artist)

        # Rung 1 — everything we have. Highest precision.
        if album or duration:
            found = self._exact(
                query, loose=False, album_name=album, duration=duration
            )
            if (terminal := self._terminal(query, found, Rung.EXACT_FULL)) is not None:
                return terminal

        # Rung 2 — most scrobbles carry no album, and duration is often absent
        # or wrong, so this is the one that does the work on real data.
        found = self._exact(query, loose=True)
        if (terminal := self._terminal(query, found, Rung.EXACT_LOOSE)) is not None:
            return terminal

        # Rung 3 — fielded search, scored.
        candidates = self._search(
            {"track_name": query.title_norm, "artist_name": query.artist_norm}
        )
        if (
            outcome := self._from_search(query, candidates, duration, Rung.SEARCH_FIELDED)
        ) is not None:
            return outcome

        # Rung 4 — freeform, same scoring. Last resort.
        candidates = self._search({"q": f"{query.artist_norm} {query.title_norm}"})
        if (
            outcome := self._from_search(query, candidates, duration, Rung.SEARCH_FREEFORM)
        ) is not None:
            return outcome

        return Resolution(query=query, rung=Rung.EXHAUSTED, candidate=None)

    def _terminal(
        self, query: Normalised, found: Candidate | None, rung: Rung
    ) -> Resolution | None:
        """Turn an `/api/get` hit into a stopping point, or `None` to continue."""
        if found is None:
            return None
        if found.instrumental:
            # §8.4: terminal. Do not retry, do not fall through to search —
            # there are no lyrics to find and a search would invent a match.
            return Resolution(
                query=query, rung=rung, candidate=found, instrumental=True
            )
        if found.plain_lyrics is None:
            return None
        return Resolution(query=query, rung=rung, candidate=found)

    def _from_search(
        self,
        query: Normalised,
        candidates: list[Candidate],
        duration: float | None,
        rung: Rung,
    ) -> Resolution | None:
        best = self._best(query, candidates, duration)
        if best is None:
            return None
        candidate, scored = best

        if scored.verdict is Verdict.REJECT:
            return None
        if candidate.instrumental:
            return Resolution(
                query=query,
                rung=rung,
                candidate=candidate,
                score=scored,
                instrumental=True,
            )
        if scored.verdict is Verdict.REVIEW:
            # CLAUDE.md §9: never auto-accept the 0.70-0.85 band. Reported as a
            # queue item, and deliberately not `resolved`.
            return Resolution(
                query=query,
                rung=rung,
                candidate=candidate,
                score=scored,
                needs_review=True,
            )
        if candidate.plain_lyrics is None:
            return None
        return Resolution(query=query, rung=rung, candidate=candidate, score=scored)
