"""SPEC §7.4 step 4 — the teach set for one song.

## Almost all of this is inherited

The frequency ranking, the zipf threshold, the closed-class exclusion, the
known-word filtering and the sort order all come from `molcajete_prep`. They
are rules about Spanish, not about books, and CLAUDE.md §4 forbids forking
them down into this repo.

**The one Rocola-specific thing is what gets passed in.**
`molcajete_prep.lexicon.build_lexicon` takes chapters, of paragraphs, of
tokens. This module hands it *one song, whose paragraphs are its unique lines*.
That single substitution is the whole of §7.4:

- `book_count` becomes an occurrence count over unique lines, so a chorus sung
  five times contributes its vocabulary once
- `first_location` points at the first unique line containing the lemma, which
  is exactly the context line a card wants (§13: one illustrative line per card
  is the ceiling, never a stanza)

No change upstream, no reimplementation here.

## Two inherited behaviours that are deliberately left alone

**The 18-card cap is reported, never enforced.** §11.1 and CLAUDE.md §6: a song
over the cap is surfaced as *dense* for the user to decide about, and never
split. Splitting a song mid-verse is incoherent in a way splitting a chapter is
not. `TrackTeachSet.is_dense` says so; nothing acts on it.

**One §5 teach rule is inert until §7.5 lands.** `mexicanism && bookCount >= 2`
promotes a regional word that would otherwise fall below the frequency floor,
and nothing sets that flag yet — `entries_for_classification()` leaves it
false, exactly as a Molcajete `--no-gloss` build does. When variety tagging
arrives it will be `variety != general` feeding the same rule. Until then a
regional word is taught only if it is frequent enough on its own merits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from molcajete_prep.classify import (
    ClassificationOptions,
    LemmaKey,
    classify_all,
    exceeds_cap,
)
from molcajete_prep.lexicon import Lexicon, LexiconRecord, build_lexicon, example_sentence
from molcajete_prep.nlp import Token, tokenize_paragraphs

from rocola_prep.teachset.stanzas import LyricDocument


@dataclass(frozen=True)
class TeachCard:
    """One lemma the song will teach, with the line that shows it in use."""

    key: LemmaKey
    lemma: str
    pos: str
    zipf: float
    #: Occurrences across the song's **unique** lines. §7.4's whole point.
    unique_line_count: int
    #: The first unique line containing the lemma. §13 allows one per card.
    example: str | None


@dataclass(frozen=True)
class TrackTeachSet:
    teach: tuple[TeachCard, ...]
    #: Underlined in the reader, never carded.
    gloss_only: tuple[LemmaKey, ...]
    lexicon: Lexicon
    #: Word tokens across unique lines — the coverage denominator.
    unique_word_tokens: int
    #: Word tokens across every line, repeats included. Reported to show the
    #: gap deduplication closed; never used in a calculation.
    total_word_tokens: int

    @property
    def is_dense(self) -> bool:
        """Over the 18-card cap. §11.1: surfaced, never acted on."""
        return len(self.teach) > 18

    @property
    def deduplication_ratio(self) -> float:
        """How much of the song was repetition. 0.0 when nothing repeated."""
        if self.total_word_tokens == 0:
            return 0.0
        return 1.0 - self.unique_word_tokens / self.total_word_tokens


def _word_tokens(paragraphs: list[list[Token]]) -> int:
    return sum(1 for tokens in paragraphs for token in tokens if token.is_word)


@dataclass(frozen=True)
class SongLexicon:
    """The lexicon and the tokens it came from, before classification.

    Exists because the glossing pass has to run *between* building this and
    classifying it: `mexicanism && bookCount >= 2` is a teach rule, so the flag
    must exist before the rules are applied. Molcajete's builder orders it the
    same way and for the same reason.
    """

    lexicon: Lexicon
    #: One song as one "chapter", whose paragraphs are the unique lines. The
    #: shape `gloss_lexicon` and `example_sentence` both expect.
    song: list[list[Token]]
    #: Every line's tokens, repeats included, in document order. The *reader*
    #: needs these — it renders the whole song — where the teach set needs
    #: `song`. Kept rather than counted and thrown away, because tokenising is
    #: the expensive part and doing it twice to get two views of one song is
    #: paying twice for the same spaCy pass.
    all_tokens: list[list[Token]]
    unique_word_tokens: int
    total_word_tokens: int


def prepare(document: LyricDocument, nlp) -> SongLexicon:
    """Tokenise the unique lines and build the lexicon. SPEC §7.4 steps 1-3."""
    unique_tokens = tokenize_paragraphs(
        nlp, [line.text for line in document.unique_lines]
    )
    all_tokens = tokenize_paragraphs(nlp, [line.text for line in document.lines])

    # One song as one "chapter". The unique lines are its paragraphs — this is
    # the substitution the module docstring is about.
    song = [unique_tokens]
    return SongLexicon(
        lexicon=build_lexicon(song),
        song=song,
        all_tokens=all_tokens,
        unique_word_tokens=_word_tokens(unique_tokens),
        total_word_tokens=_word_tokens(all_tokens),
    )


def classify_song(
    prepared: SongLexicon,
    *,
    known_lemmas: frozenset[str] = frozenset(),
    mexicanism: Mapping[LemmaKey, bool] | None = None,
    options: ClassificationOptions | None = None,
) -> TrackTeachSet:
    """SPEC §7.4 step 4, over an already-built lexicon.

    `mexicanism` comes from the glossing pass. Omitting it leaves every entry
    false, which is the state a Molcajete `--no-gloss` build is in and the
    state this repo is in until §7.5 lands.
    """
    options = options or ClassificationOptions()
    lexicon = prepared.lexicon
    song = prepared.song

    results = classify_all(
        lexicon.entries_for_classification(mexicanism), known_lemmas, options
    )

    def record_of(key: LemmaKey) -> LexiconRecord:
        return lexicon.records[key]

    teach_keys = [key for key, result in results.items() if result.is_teach]
    # §5 Step 3's order, as `assign_to_chapters` does it: most-used first, so an
    # abandoned session still taught the most useful words. Ties break on the
    # key so rebuilds stay byte-identical.
    teach_keys.sort(key=lambda key: (-record_of(key).book_count, key))

    teach = tuple(
        TeachCard(
            key=key,
            lemma=record_of(key).lemma,
            pos=record_of(key).pos,
            zipf=record_of(key).zipf,
            unique_line_count=record_of(key).book_count,
            example=(
                found[0] if (found := example_sentence(record_of(key), song)) else None
            ),
        )
        for key in teach_keys
    )

    gloss_only = tuple(
        sorted(key for key, result in results.items() if not result.is_teach)
    )

    return TrackTeachSet(
        teach=teach,
        gloss_only=gloss_only,
        lexicon=lexicon,
        unique_word_tokens=prepared.unique_word_tokens,
        total_word_tokens=prepared.total_word_tokens,
    )


def build_teach_set(
    document: LyricDocument,
    nlp,
    *,
    known_lemmas: frozenset[str] = frozenset(),
    mexicanism: Mapping[LemmaKey, bool] | None = None,
    options: ClassificationOptions | None = None,
) -> TrackTeachSet:
    """SPEC §7.4, in one call. One song in, one teach set out.

    The convenience path, for callers with no glossing pass to interleave.
    A build that glosses uses `prepare` and `classify_song` around it.
    """
    return classify_song(
        prepare(document, nlp),
        known_lemmas=known_lemmas,
        mexicanism=mexicanism,
        options=options,
    )


__all__ = [
    "SongLexicon",
    "TeachCard",
    "TrackTeachSet",
    "build_teach_set",
    "classify_song",
    "exceeds_cap",
    "prepare",
]
