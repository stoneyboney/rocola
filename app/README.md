# rocola — the app

The device half of Rocola. A React PWA that teaches a song's vocabulary as
flashcards, then lets you read the lyrics.

It makes **no network calls at runtime**. Lyrics and glosses are prepared on the
desktop and imported; after one visit and one import it works in airplane mode.

Live at https://stoneyboney.github.io/rocola/

## Running it

```bash
npm install
npm run dev        # http://localhost:5173/rocola/
npm test           # the domain suite
npm run build      # typecheck, then bundle
npm run preview    # serve the built output
```

The service worker is disabled in `dev`. To exercise it, `npm run build &&
npm run preview`.

## Storage identifiers — read this before adding one

Rocola and Molcajete are both served from `stoneyboney.github.io`. **IndexedDB,
Cache Storage and localStorage are scoped to the origin, not the path.** The
service worker's scope *is* path-based and will look correct, which is what
makes the collision easy to miss.

Everything this app owns is `rocola`-prefixed:

| Kind | Where | Value |
|---|---|---|
| IndexedDB database | `src/infra/db.ts` | `rocola` |
| Cache Storage prefix | `workbox.cacheId` in `vite.config.ts` | `rocola` |
| localStorage / sessionStorage | — | none exist |

There is no hand-written service worker; `vite-plugin-pwa` generates it. Without
`cacheId`, workbox would name its caches after the registration scope — which
differs between the apps, but only by accident, and only until someone adds a
`runtimeCaching` rule with an explicit `cacheName`. Do not remove it.

`navigator.storage.persist()` is origin-scoped too, and is deliberately shared.
There is one grant per origin and nothing to namespace.

## Deploying

```bash
git push
```

`.github/workflows/deploy.yml` runs the tests, builds `app/`, and publishes. A
red test does not get published.

`base` in `vite.config.ts` is `/rocola/` and the manifest's `start_url` and
`scope` have to agree with it. Renaming the repo means changing all three.

## What is here, and what is not

This is the fork commit. The reader, the song list and the last.fm pipeline are
Phase 3; what survives from Molcajete is the part that was never about books.

```
src/domain/      Pure. No React, no DOM, no Dexie. Heavily tested.
  types.ts       Tokens and the lexicon. Paragraph and BookId keep their
                 inherited names until Track and LyricDocument exist.
  lemma.ts       LemmaKey (text-scoped) vs LemmaId (global). Read this first.
  teachSet.ts    Which words get taught. The closed-class rule lives here.
  coverage.ts    Lemma counts and the coverage figure. Threshold 0.95.
  srs/           FSRS, behind one seam. The only file importing ts-fsrs.
  session/       The teaching reducer. Effects are data, not actions.
  review/        The cross-song due queue.
src/infra/       Dexie. Three stores, one schema version.
src/ui/          Components. They compute nothing.
src/app/         Wiring, routing, import.
```

Two screens: `Home` and `Review`. `TeachingSession` is built and tested but has
no caller — it needs a song, and there are none yet.

## Rules that are easy to break by accident

- **`src/domain/` imports nothing from React, the DOM, or Dexie.** It is a
  library that happens to be consumed by a web app, and it gets ported to Swift.
- **Components receive finished view models.** No filtering, date maths or FSRS
  logic in a component.
- **The whole FSRS card object is stored**, never a subset. Partial state cannot
  be rescheduled.
- **Coverage never gates anything.** It is a number shown to the reader.
- **No lyric text in this repository**, including test fixtures. `tests/fixture.ts`
  is invented Spanish written for the test.
