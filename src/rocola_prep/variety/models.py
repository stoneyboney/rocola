"""SPEC §6.3 — the schema change that makes Rocola not-Molcajete.

Molcajete could assume every gloss was Mexican and carried one boolean to say
so. A pan-Hispanic rotation cannot: SPEC §9.1's failure is a reader who learns
`pibe` from Argentine rock and says it in Monterrey.

So a sense records *which* Spanish it belongs to, and what the reader's own
dialect would say instead. Read anything; reinforce only what you need to
produce.

## `general` wins whenever anything is unclear

CLAUDE.md §5: over-tagging is the expected model failure mode, and when the
provider is uncertain, `general` wins. That is enforced here rather than asked
for in the prompt — `parse_variety` returns `GENERAL` for anything it does not
recognise, so a model that invents `es-419` or answers `"mexican"` produces an
untagged sense rather than a crash or a wrong badge.

The asymmetry is deliberate. A word wrongly marked `general` is a badge the
reader does not see. A word wrongly marked `es-AR` is a badge that is *lying*,
and SPEC §9.2 renders it next to "MX: …" as though it were a fact.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Variety(str, Enum):
    """SPEC §6.3. `general` is pan-Hispanic and is the default and the fallback."""

    GENERAL = "general"
    MX = "es-MX"
    AR = "es-AR"
    ES = "es-ES"
    CO = "es-CO"
    CL = "es-CL"
    PE = "es-PE"
    VE = "es-VE"
    PR = "es-PR"
    DO = "es-DO"
    CU = "es-CU"
    UY = "es-UY"
    EC = "es-EC"
    GT = "es-GT"
    BO = "es-BO"
    PY = "es-PY"
    CR = "es-CR"
    PA = "es-PA"
    HN = "es-HN"
    SV = "es-SV"
    NI = "es-NI"

    @property
    def is_regional(self) -> bool:
        return self is not Variety.GENERAL

    @property
    def badge(self) -> str:
        """The two-letter code SPEC §9.2 puts on the card back. Empty for general."""
        return "" if self is Variety.GENERAL else self.value.removeprefix("es-")


class Register(str, Enum):
    """SPEC §6.3. `albur` is Mexican wordplay and is why this is not a boolean."""

    NEUTRAL = "neutral"
    COLOQUIAL = "coloquial"
    VULGAR = "vulgar"
    POETIC = "poetic"
    ARCAIC = "arcaic"
    ALBUR = "albur"


def parse_variety(value: Any) -> Variety:
    """Any input to a `Variety`. Unrecognised input is `general`, never an error.

    Accepts `es-MX`, `es_mx`, `MX` and `mx`, because a model asked for one
    format will eventually answer in another and rejecting the batch over
    punctuation would cost a retry for nothing.
    """
    if isinstance(value, Variety):
        return value
    if not isinstance(value, str):
        return Variety.GENERAL

    text = value.strip().replace("_", "-").lower()
    if not text or text == "general":
        return Variety.GENERAL

    code = text.removeprefix("es-").upper()
    for member in Variety:
        if member is not Variety.GENERAL and member.value.removeprefix("es-") == code:
            return member
    return Variety.GENERAL


def parse_register(value: Any) -> Register:
    """Any input to a `Register`. Unrecognised input is `neutral`."""
    if isinstance(value, Register):
        return value
    if not isinstance(value, str):
        return Register.NEUTRAL
    text = value.strip().lower()
    for member in Register:
        if member.value == text:
            return member
    return Register.NEUTRAL


@dataclass(frozen=True)
class VarietySense:
    """One lemma's sense, as SPEC §6.3 describes it.

    `de` and `en` are here rather than left to `molcajete_prep.Gloss` because
    §7.5's model pass returns them in the same answer — asking twice would be
    two model passes over one lemma to fill in one record.
    """

    lemma: str
    pos: str
    de: str | None = None
    en: str | None = None
    variety: Variety = Variety.GENERAL
    register: Register = Register.NEUTRAL

    #: §6.3: populated only when `variety` is neither general nor the home
    #: dialect. What a speaker at home would actually say.
    home_equivalent: str | None = None
    home_equivalent_note: str | None = None

    #: §9.3: voseo and vosotros forms — recognisable, never drilled.
    morph_note: str | None = None

    confidence: float | None = None

    @property
    def identity(self) -> tuple[str, str]:
        return (self.lemma, self.pos)

    def needs_badge(self, home_dialect: Variety) -> bool:
        """SPEC §9.2's table, in one line.

        No badge for `general`, and none for the reader's own dialect — in
        Monterrey, a Monterrey word is just a word.
        """
        return self.variety.is_regional and self.variety is not home_dialect

    def normalised(self, home_dialect: Variety) -> VarietySense:
        """The invariants §6.3 states, enforced rather than trusted.

        A pan-Hispanic sense cannot have a home equivalent, and neither can one
        already in the home dialect: `homeEquivalent` answers "what would you
        say instead", and there is no instead. CLAUDE.md §5 forbids populating
        it with a synonym for its own sake, and a model that ignores that
        instruction is the expected case rather than a surprising one.
        """
        if self.needs_badge(home_dialect):
            return self
        return VarietySense(
            lemma=self.lemma,
            pos=self.pos,
            de=self.de,
            en=self.en,
            variety=self.variety,
            register=self.register,
            home_equivalent=None,
            home_equivalent_note=None,
            morph_note=self.morph_note,
            confidence=self.confidence,
        )
