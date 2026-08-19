# rocola

A Spanish song-lyrics reader. Pre-teach the vocabulary of a song, then read it
with the words already in place.

Forked from [Molcajete](https://github.com/stoneyboney/molcajete), which does
the same thing to book chapters. The two share their language half — spaCy, the
lexicon, glossing, the teach rules — as the `molcajete-prep` package, and share
nothing else.

*Una rocola* is a jukebox.

## Layout

```
src/rocola_prep/   The song half. Python, desktop only.
  lastfm/          Scrobble history and the selection heuristic
  lrclib/          The lyrics client. Plain lyrics only.
  matcher/         Scrobble -> LRCLIB. The highest-risk component.
  langfilter/      Is this actually Spanish, judged on the lyric text
  variety/         Dialect tagging and the home-dialect equivalent
tests/             Synthetic Spanish only. Never real lyric text.
app/               The PWA. React + TypeScript + Vite.
docs/              Molcajete's SPEC and CLAUDE, which remain in force.
```

All five prep packages are empty. This is the fork, not the pipeline.

## Running it

```bash
uv sync                       # needs ../molcajete-prep checked out beside this
uv run pytest

cd app && npm install
npm test
npm run dev                   # http://localhost:5173/rocola/
```

`molcajete-prep` is resolved from `../molcajete-prep` as an editable install, so
the three repos want to sit side by side:

```
~/Projects/molcajete
~/Projects/molcajete-prep
~/Projects/rocola
```

## Configuration

Copy `.env.example` to `.env` and fill in a last.fm API key. `.env` is
gitignored; `.env.example` is the template and holds no value.

## Two rules worth reading before writing any code

**No lyric text in this repository.** Not in fixtures, not in tests, not in
docs, not in commit messages. Lyrics are fetched at runtime and stored on the
user's own device. Tests use synthetic Spanish written for the test. See
`CLAUDE.md` §2.

**Storage identifiers are `rocola`-prefixed, always.** This app and Molcajete
share the origin `stoneyboney.github.io`, where IndexedDB and Cache Storage are
scoped to the origin and not the path. See `CLAUDE.md` §3.

Read `SPEC.md` and `CLAUDE.md` before starting. `docs/molcajete-CLAUDE.md`
still applies except where Rocola's overrides it.
