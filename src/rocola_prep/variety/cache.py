"""Where a tagged sense is remembered.

Separate from `molcajete_prep`'s gloss cache, and not by accident. That cache
stores `Gloss`, which has nowhere to put a variety, and CLAUDE.md §4 forbids
teaching the shared package about `homeEquivalent` — a Rocola concept that
would have to grow a `homeDialect` alongside it to mean anything.

## Five things in the key, and each earns its place

    lemma, pos          which word, in which sense
    model               a 12B answer and a frontier answer are different claims
    prompt_version      the instructions that produced it
    home_dialect        the one that would otherwise rot silently

**`home_dialect` is the interesting one.** SPEC §15 q4 records the limitation:
`homeEquivalent` is generated against one home dialect at gloss time, so
switching later requires a re-gloss pass. Putting it in the key turns that from
a documented caveat into a cache miss — move home to Buenos Aires and the
Mexican equivalents are simply not found, rather than found and wrong.

## What is not in here

Lyric text. A row is a lemma, a two-word gloss and a label. CLAUDE.md §2 is
about lyrics rather than vocabulary, and a gloss is vocabulary — but the
example line that justified the gloss is *not* stored, because a line of a song
is a line of a song wherever it is written down.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from rocola_prep.variety.models import (
    Register,
    Variety,
    VarietySense,
    parse_register,
    parse_variety,
)

Identity = tuple[str, str]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS senses (
    lemma                TEXT NOT NULL,
    pos                  TEXT NOT NULL,
    model                TEXT NOT NULL,
    prompt_version       INTEGER NOT NULL,
    home_dialect         TEXT NOT NULL,
    de                   TEXT,
    en                   TEXT,
    variety              TEXT NOT NULL,
    register             TEXT NOT NULL,
    home_equivalent      TEXT,
    home_equivalent_note TEXT,
    morph_note           TEXT,
    confidence           REAL,
    created_at           TEXT NOT NULL,
    PRIMARY KEY (lemma, pos, model, prompt_version, home_dialect)
)
"""

_COLUMNS = (
    "lemma, pos, de, en, variety, register, home_equivalent, "
    "home_equivalent_note, morph_note, confidence"
)


class VarietyCache:
    """Tagged senses, scoped to the model, the prompt and the home dialect."""

    def __init__(
        self,
        path: Path | str,
        *,
        model: str,
        prompt_version: int,
        home_dialect: Variety,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.model = model
        self.prompt_version = prompt_version
        self.home_dialect = home_dialect
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.execute(_SCHEMA)
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> VarietyCache:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @property
    def _scope(self) -> tuple[str, int, str]:
        return (self.model, self.prompt_version, self.home_dialect.value)

    def get(self, identity: Identity) -> VarietySense | None:
        row = self._db.execute(
            f"SELECT {_COLUMNS} FROM senses"
            " WHERE lemma = ? AND pos = ?"
            "   AND model = ? AND prompt_version = ? AND home_dialect = ?",
            (*identity, *self._scope),
        ).fetchone()
        return _sense_from(row) if row else None

    def get_many(self, identities: list[Identity]) -> dict[Identity, VarietySense]:
        """Every hit among `identities`. Misses are simply absent."""
        found: dict[Identity, VarietySense] = {}
        for identity in identities:
            sense = self.get(identity)
            if sense is not None:
                found[identity] = sense
        return found

    def put(self, sense: VarietySense, *, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        self._db.execute(
            "INSERT INTO senses (lemma, pos, model, prompt_version, home_dialect,"
            " de, en, variety, register, home_equivalent, home_equivalent_note,"
            " morph_note, confidence, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(lemma, pos, model, prompt_version, home_dialect) DO UPDATE SET"
            "   de = excluded.de, en = excluded.en,"
            "   variety = excluded.variety, register = excluded.register,"
            "   home_equivalent = excluded.home_equivalent,"
            "   home_equivalent_note = excluded.home_equivalent_note,"
            "   morph_note = excluded.morph_note,"
            "   confidence = excluded.confidence,"
            "   created_at = excluded.created_at",
            (
                sense.lemma,
                sense.pos,
                *self._scope,
                sense.de,
                sense.en,
                sense.variety.value,
                sense.register.value,
                sense.home_equivalent,
                sense.home_equivalent_note,
                sense.morph_note,
                sense.confidence,
                now.isoformat(),
            ),
        )
        self._db.commit()

    def put_many(self, senses: dict[Identity, VarietySense]) -> None:
        for sense in senses.values():
            self.put(sense)

    def columns(self) -> list[str]:
        return [r[1] for r in self._db.execute("PRAGMA table_info(senses)")]

    def count(self) -> int:
        row = self._db.execute("SELECT count(*) FROM senses").fetchone()
        return int(row[0]) if row else 0


def _sense_from(row: tuple) -> VarietySense:
    return VarietySense(
        lemma=row[0],
        pos=row[1],
        de=row[2],
        en=row[3],
        variety=parse_variety(row[4]),
        register=parse_register(row[5]),
        home_equivalent=row[6],
        home_equivalent_note=row[7],
        morph_note=row[8],
        confidence=row[9],
    )


__all__ = ["Identity", "Register", "Variety", "VarietyCache"]
