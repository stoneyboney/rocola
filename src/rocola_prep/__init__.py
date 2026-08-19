"""Rocola's own prep half: scrobbles in, a glossed teach set out.

The language work — spaCy, the lexicon, the teach rules, glossing, the Anki
seed — is **not** here. It lives in `molcajete-prep`, a shared package this
one depends on and which Molcajete depends on too. CLAUDE.md §4: fixes to
glossing, lemmatisation, Wiktionary lookup, frequency ranking or the teach-set
core belong upstream there, never copied down into this repo.

What is here is everything that knows what a song is:

    lastfm/      scrobble history, and the selection heuristic over it
    lrclib/      the lyrics client. Plain lyrics only; synced is discarded
    matcher/     scrobble -> LRCLIB. The highest-risk component, SPEC §8
    langfilter/  is this actually Spanish, judged on the lyric text
    variety/     dialect tagging, and the home-dialect equivalent

All five are empty. This is the fork commit, not the pipeline.
"""

__version__ = "0.1.0"
