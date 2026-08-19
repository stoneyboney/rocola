"""SPEC §8.1 — turning a scrobble into something LRCLIB can be asked about.

last.fm scrobbles are user-submitted and inconsistent; LRCLIB's `/api/get`
matches strictly. This module is the whole of the gap between those two facts.

## Two strings out, not one

Every field produces both a **norm** and a **key**:

    titleNorm   "corazón espinado"        accents kept
    titleKey    "corazon espinado"        accents folded

The key is what comparisons run against, because a scrobble that says
`Corazon Espinado` and a catalogue that says `Corazón Espinado` are the same
song and no useful matcher may disagree. The norm exists because the key throws
away information a human needs to read — SPEC §8.1 keeps it as a display
fallback, and it is the more legible of the two when a miss is being examined
by hand.

## Normalisation is for comparison only

CLAUDE.md §9 is explicit, and it is the rule most easily broken by accident:
**the original strings are what get displayed, always.** Nothing here mutates
the scrobble. `Normalised` carries `title` and `artist` verbatim alongside the
derived forms precisely so that a caller holding one of these has no reason to
reach for a normalised string when showing something to a person.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# The stop-list. SPEC §8.1 rule 2.
# ---------------------------------------------------------------------------
#
# CLAUDE.md §9: *never* strip a parenthetical unless its content matches one of
# these. That restraint is the entire point of having a list rather than a rule
# like "drop trailing parentheses" — real titles are full of them, and the ones
# worth keeping outnumber the ones worth dropping:
#
#     "Marta, Sebas, Guille y los demás"     no parenthetical at all
#     "Augen zu (Es regnet Blumen)"          parenthetical IS the title
#     "Como La Flor (Live/Remastered 2026)"  qualifier, strip it
#
# Ordered longest-first where one pattern is a prefix of another, so that
# `2011 remaster` is not left as a bare `2011` by an eager `remaster`.
_QUALIFIERS = [
    r"\d{4}\s+remaster(?:ed)?",
    r"remaster(?:ed)?(?:\s+\d{4})?",
    r"single\s+version",
    r"album\s+version",
    r"radio\s+edit",
    r"bonus\s+track",
    r"en\s+vivo",
    r"versi[óo]n\s+.*",
    r"live(?:/.*)?",
    r"deluxe",
    r"explicit",
    r"clean",
    r"mono",
    r"stereo",
    r"demo",
    r"remix",
]

# A parenthetical or bracketed run whose *entire* content is qualifiers, allowing
# several to be slash- or comma-joined: "(Live/Remastered 2026)" is one group of
# two, and both have to match or the group stays.
_ONE = "|".join(_QUALIFIERS)
_QUALIFIER_GROUP = re.compile(
    rf"\s*[\(\[]\s*(?:{_ONE})(?:\s*[/,&+-]\s*(?:{_ONE}))*\s*[\)\]]\s*",
    re.IGNORECASE,
)

# The same list again, as a trailing ` - <qualifier>` suffix (rule 4). Anchored
# to the end so that a dash inside a title survives: `Marta, Sebas - Guille`
# would not be touched, because `Guille` is not a qualifier.
_QUALIFIER_SUFFIX = re.compile(
    rf"\s+-\s+(?:{_ONE})(?:\s*[/,&+-]\s*(?:{_ONE}))*\s*$",
    re.IGNORECASE,
)

# Rule 3. `feat.`/`ft.`/`con ` and everything after it, whether it is wrapped in
# brackets or just trails. `con ` needs the trailing space or it eats the first
# syllable of every word starting "con" — `Contigo`, `Conmigo`, `Constante`.
_FEATURING = re.compile(
    r"\s*[\(\[]?\s*\b(?:feat\.?|ft\.?|featuring|con)\s+.*$",
    re.IGNORECASE,
)

# Rule 4's first half. Every dash variant becomes the ASCII one first, so the
# suffix pattern above only has to know about `-`.
_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class Normalised:
    """A scrobble, in every form the matcher needs it.

    `title` and `artist` are the originals, untouched. CLAUDE.md §9: they are
    what gets displayed, and they are carried here so that a caller never has a
    reason to display one of the derived forms instead.
    """

    title: str
    artist: str
    title_norm: str
    artist_norm: str
    title_key: str
    artist_key: str

    @property
    def key(self) -> tuple[str, str]:
        """`(artistKey, titleKey)` — the cache key SPEC §8.3 specifies."""
        return (self.artist_key, self.title_key)


def fold_accents(text: str) -> str:
    """Strip diacritics for comparison. `ñ→n`, `á→a`.

    NFKD splits a precomposed character into its base plus a combining mark;
    dropping the marks leaves the base. This is why it is stdlib rather than a
    dependency — the whole operation is two lines and Spanish needs nothing
    cleverer.

    Applied to the **key only**. Folding is lossy in a way that matters to a
    reader: `año` and `ano` are different words, and only one of them is a year.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _strip_qualifiers(text: str) -> str:
    """Rules 2 and 4: bracketed qualifiers, then trailing ` - qualifier`.

    Looped because a title can carry more than one — `(Live) (Remastered)` —
    and one pass leaves the second.
    """
    previous = None
    while previous != text:
        previous = text
        text = _QUALIFIER_GROUP.sub(" ", text)
        text = _QUALIFIER_SUFFIX.sub("", text)
    return text


def normalise_title(title: str) -> str:
    """SPEC §8.1 rules 1–5, for a track title."""
    text = unicodedata.normalize("NFKC", title).lower()
    text = text.translate(_DASHES)
    text = _strip_qualifiers(text)
    text = _FEATURING.sub("", text)
    text = _strip_qualifiers(text)
    return _WHITESPACE.sub(" ", text).strip(" -")


def normalise_artist(artist: str) -> str:
    """SPEC §8.1 rules 1–5, for an artist.

    Rule 3 says to retain the **primary artist only**. last.fm credits
    collaborations in the artist field with every separator anyone has ever
    used, so a `Die Toten Hosen, Blixa Bargeld & Einstürzende Neubauten` has to
    come down to its first name before it is asked about — LRCLIB catalogues
    the primary.
    """
    text = unicodedata.normalize("NFKC", artist).lower()
    text = text.translate(_DASHES)
    text = _strip_qualifiers(text)
    text = _FEATURING.sub("", text)
    # The primary artist is whatever precedes the first collaboration marker.
    text = re.split(r"\s*(?:,|&|\bvs\.?\b|\bwith\b|\by\b(?=\s))\s*", text)[0]
    return _WHITESPACE.sub(" ", text).strip(" -")


def normalise(title: str, artist: str) -> Normalised:
    """Both fields, both forms. The only entry point callers should need."""
    title_norm = normalise_title(title)
    artist_norm = normalise_artist(artist)
    return Normalised(
        title=title,
        artist=artist,
        title_norm=title_norm,
        artist_norm=artist_norm,
        title_key=fold_accents(title_norm),
        artist_key=fold_accents(artist_norm),
    )
