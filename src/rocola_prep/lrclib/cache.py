"""SPEC §8.3 — remembering what the ladder concluded, so it runs once.

## Misses are cached too, and that is the point

A hit is cheap to rediscover: one `/api/get` and you have it back. A **miss**
costs the whole ladder — four requests, two of them scored searches — and a
rotation is mostly the same tracks week after week. Caching only hits would mean
every pass paying full price for every track LRCLIB does not have, which is the
half of the catalogue that is not going to shrink.

§8.3 also says to **re-check misses monthly**: LRCLIB is crowdsourced and grows,
so a track with no lyrics today may have them in six weeks. A permanent miss
would be a decision made once, in ignorance, and never revisited.

## What is not in here

**Lyric text.** Not the plain text, not a hash of it, not a prefix. This table
holds an id, a rung, a status and a timestamp — enough to skip the ladder and
nothing more.

That is a CLAUDE.md §2 requirement rather than a size optimisation. A cache is
a file on disk that outlives the process, and §2 says lyric text may not settle
anywhere it could be committed. `cache/` is gitignored, but "gitignored" is one
`git add -f` away from not being true, and the rule is worth enforcing where it
cannot be undone by a flag. There is a test asserting the schema has no column
that could hold text.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rocola_prep.lrclib.client import Resolution, Rung

#: §8.3: "Re-check misses monthly."
MISS_TTL = timedelta(days=30)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS resolutions (
    artist_key  TEXT NOT NULL,
    title_key   TEXT NOT NULL,
    status      TEXT NOT NULL,
    rung        INTEGER NOT NULL,
    lrclib_id   INTEGER,
    checked_at  TEXT NOT NULL,
    PRIMARY KEY (artist_key, title_key)
)
"""


@dataclass(frozen=True)
class CachedResolution:
    artist_key: str
    title_key: str
    status: str
    rung: Rung
    lrclib_id: int | None
    checked_at: datetime

    @property
    def is_miss(self) -> bool:
        return self.status in {"no_lyrics", "review"}

    def is_stale(self, now: datetime) -> bool:
        """Misses expire after 30 days. Hits and instrumentals do not.

        An instrumental is terminal per §8.4 — the track has no lyrics to
        acquire later — so re-checking it would be asking a question whose
        answer cannot change.
        """
        if not self.is_miss:
            return False
        return now - self.checked_at >= MISS_TTL


class ResolutionCache:
    """The §8.3 cache, keyed `(artistKey, titleKey)`."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path)
        self._db.execute(_SCHEMA)
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> ResolutionCache:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get(
        self, key: tuple[str, str], *, now: datetime | None = None
    ) -> CachedResolution | None:
        """The cached answer, or `None` if absent or a miss that has gone stale."""
        now = now or datetime.now(timezone.utc)
        artist_key, title_key = key
        row = self._db.execute(
            "SELECT artist_key, title_key, status, rung, lrclib_id, checked_at"
            " FROM resolutions WHERE artist_key = ? AND title_key = ?",
            (artist_key, title_key),
        ).fetchone()
        if row is None:
            return None

        cached = CachedResolution(
            artist_key=row[0],
            title_key=row[1],
            status=row[2],
            rung=Rung(row[3]),
            lrclib_id=row[4],
            checked_at=datetime.fromisoformat(row[5]),
        )
        return None if cached.is_stale(now) else cached

    def put(self, resolution: Resolution, *, now: datetime | None = None) -> None:
        """Record what the ladder concluded. Stores no lyric text."""
        now = now or datetime.now(timezone.utc)
        self._db.execute(
            "INSERT INTO resolutions"
            " (artist_key, title_key, status, rung, lrclib_id, checked_at)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(artist_key, title_key) DO UPDATE SET"
            "   status = excluded.status,"
            "   rung = excluded.rung,"
            "   lrclib_id = excluded.lrclib_id,"
            "   checked_at = excluded.checked_at",
            (
                resolution.query.artist_key,
                resolution.query.title_key,
                resolution.status,
                int(resolution.rung),
                resolution.candidate.id if resolution.candidate else None,
                now.isoformat(),
            ),
        )
        self._db.commit()

    def columns(self) -> list[str]:
        """The schema, for the test that asserts no column could hold text."""
        return [r[1] for r in self._db.execute("PRAGMA table_info(resolutions)")]
