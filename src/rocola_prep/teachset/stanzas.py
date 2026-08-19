"""SPEC §6.2's document, and §7.4's first three steps.

Turns LRCLIB plain text into the structure both the reader and the teach-set
builder read — from opposite ends, which is the whole design:

    the reader gets    every line, in order, with repeats marked
    the builder gets   the unique lines only

A chorus sung five times is five lines on the page and one line in the count.
SPEC §7.4 explains what goes wrong otherwise: the repeated vocabulary looks
five times as common as it is, sorts to the top of the teach set, and the
builder teaches the hook while skipping the verses — backwards, because the
hook is the part repetition teaches you for free.

## Lyrics are not prose

§10.1: line breaks are preserved exactly as fetched and must never be reflowed
into paragraphs. So a `Line` is a line because the lyricist ended it there, not
because it reached a width. Blank lines delimit stanzas and nothing else does.

## What the hash folds away, and why that is not the display form

Two lines count as the same line when their **normalised, accent-folded,
punctuation-stripped** text matches (§7.4 step 1). That folding is for
comparison only — the same rule the matcher lives by (CLAUDE.md §9) — because
a chorus written `¡Ay, corazón!` the first time and `Ay corazón` the second is
one chorus, and a reader shown the second version instead of what was fetched
would notice.

`Line.text` is therefore always the text as fetched. `Line.key` is what the
counting uses and what nothing renders.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from rocola_prep.matcher.normalise import fold_accents

_WHITESPACE = re.compile(r"\s+")


def _strip_punctuation(text: str) -> str:
    """Drop every punctuation and symbol character, by Unicode category.

    Tested per character rather than matched against a precompiled class. The
    class was the first attempt and it was wrong: building it from `range(0x2000)`
    silently excluded the whole General Punctuation block, so an em dash — the
    one lyricists actually use — survived and `Ay — corazón` did not match
    `Ay corazón`.

    Replaced with a space rather than removed, so that `ay,corazón` becomes two
    words rather than one. `_WHITESPACE` collapses whatever that doubles up, and
    an apostrophe inside `pa'` still disappears without splitting the word,
    because the trailing space is then stripped.
    """
    return "".join(
        " " if unicodedata.category(c).startswith(("P", "S")) else c for c in text
    )


def line_key(text: str) -> str:
    """SPEC §7.4 step 1's hash input. For comparison only; never displayed."""
    folded = fold_accents(unicodedata.normalize("NFKC", text).lower())
    return _WHITESPACE.sub(" ", _strip_punctuation(folded)).strip()


@dataclass(frozen=True)
class Line:
    #: Global line index across the document, as SPEC §6.2 specifies.
    index: int
    #: Exactly as fetched. §10.1 — this is what gets rendered.
    text: str
    #: The comparison form. Two lines are "the same line" when these match.
    key: str
    #: The index of the first line carrying this key, or None if this is it.
    repeat_of: int | None = None

    @property
    def is_repeat(self) -> bool:
        return self.repeat_of is not None

    @property
    def is_blank(self) -> bool:
        return not self.key


@dataclass(frozen=True)
class Stanza:
    index: int
    lines: tuple[Line, ...]
    #: Set when this stanza duplicates an earlier one (§7.4 step 3). The reader
    #: de-emphasises these rather than hiding them (§10.1).
    repeat_of: int | None = None

    @property
    def key(self) -> str:
        """The stanza's identity: its lines' keys, in order."""
        return "\n".join(line.key for line in self.lines)

    @property
    def is_repeat(self) -> bool:
        return self.repeat_of is not None


@dataclass(frozen=True)
class LyricDocument:
    """SPEC §6.2. Stanzas for the reader, unique lines for the builder."""

    stanzas: tuple[Stanza, ...] = field(default_factory=tuple)

    @property
    def lines(self) -> tuple[Line, ...]:
        """Every line, in document order, repeats included."""
        return tuple(line for stanza in self.stanzas for line in stanza.lines)

    @property
    def unique_lines(self) -> tuple[Line, ...]:
        """SPEC §7.4 step 2: first occurrence of each key, in document order.

        This is what the teach-set builder counts over, and the only reason the
        builder differs from Molcajete's at all.
        """
        return tuple(line for line in self.lines if not line.is_repeat)

    @property
    def repeated_line_count(self) -> int:
        return sum(1 for line in self.lines if line.is_repeat)

    @property
    def repeated_stanza_count(self) -> int:
        return sum(1 for stanza in self.stanzas if stanza.is_repeat)


def parse_document(plain_lyrics: str) -> LyricDocument:
    """Split LRCLIB plain text into stanzas, marking every repeat.

    Blank lines delimit stanzas (§6.2). Runs of blank lines collapse into one
    delimiter rather than producing empty stanzas, because LRCLIB submissions
    are inconsistent about spacing and an empty stanza is not a thing the reader
    can render.
    """
    blocks: list[list[str]] = []
    current: list[str] = []
    for raw in plain_lyrics.splitlines():
        if raw.strip():
            current.append(raw)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)

    seen_lines: dict[str, int] = {}
    seen_stanzas: dict[str, int] = {}
    stanzas: list[Stanza] = []
    line_index = 0

    for stanza_index, block in enumerate(blocks):
        lines: list[Line] = []
        for text in block:
            key = line_key(text)
            # A line that is only punctuation folds to "" and would otherwise
            # make every such line a repeat of the first one.
            repeat_of = seen_lines.get(key) if key else None
            if key and key not in seen_lines:
                seen_lines[key] = line_index
            lines.append(Line(index=line_index, text=text, key=key, repeat_of=repeat_of))
            line_index += 1

        stanza = Stanza(index=stanza_index, lines=tuple(lines))
        repeat_of = seen_stanzas.get(stanza.key)
        if repeat_of is None:
            seen_stanzas[stanza.key] = stanza_index
        else:
            stanza = Stanza(
                index=stanza_index, lines=tuple(lines), repeat_of=repeat_of
            )
        stanzas.append(stanza)

    return LyricDocument(stanzas=tuple(stanzas))
