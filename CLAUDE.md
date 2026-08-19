# CLAUDE.md — Rocola

Hard constraints for code generation in this repository. These are not suggestions. If a requested change would violate one of these, stop and say so rather than implementing it.

Companion documents: `SPEC.md`, `docs/molcajete-SPEC.md`, `docs/molcajete-CLAUDE.md`

---

## 0. Inheritance

Rocola is forked from Molcajete. **All constraints in `docs/molcajete-CLAUDE.md` remain in force** except where explicitly overridden below. In particular the four Swift-portability rules still apply — no framework-specific logic outside the view layer, no browser APIs in the domain layer, plain serialisable state, and no dependency on React lifecycle for correctness.

---

## 1. Scope constraints — do not build these

Rocola is a **reading** app. The following are out of scope and must not be added, not even behind a flag, not even "while we're in there":

- Time-synced lyrics, LRC parsing, timestamp handling
- Audio playback of any kind; no `<audio>` element, no player component
- Spotify Web Playback SDK, Apple MusicKit, any streaming SDK
- Whisper, forced alignment, speech processing
- Cloze, dictation, or listening exercises

**Discard every timed or serialised lyric field, whatever it is called.** Keep
`plainLyrics` and nothing else. Do not store the others "in case we need it
later."

This is written as a rule about *kinds* of field rather than a list of names,
because the list was already wrong once. SPEC §7.2 names `plainLyrics` and
`syncedLyrics`; LRCLIB also returns **`lyricsfile`**, a YAML document holding
the timed lines *and* a second full copy of the plain text — 2,821 characters
against `plainLyrics`' 677 on the track it was measured on. A client written to
"discard `syncedLyrics`" would have kept both the timestamps and the text.

So the client **allowlists** the fields it keeps rather than denylisting the
ones it drops, and does it on the raw JSON before a response object exists. A
fourth lyric-bearing field added by LRCLIB next year is then already handled.

The only permitted streaming touchpoint is an outbound deep link built from a stored track ID. No SDK, no embed, no OAuth for playback.

---

## 2. Lyric text handling

> **Never bundle, commit, or redistribute lyric text.**

- No lyric text in the repository. Not in fixtures, not in tests, not in docs, not in comments, not in commit messages.
- **Tests use synthetic Spanish text**, written for the test. If a test needs stanza structure, invent stanzas.
- No server-side lyric cache. No cross-device sync of lyric content. Local storage on the user's own device only.
- No bulk export path that emits lyric text.
- Anki export carries **vocabulary cards only**. One illustrative context line per card is the ceiling; never a stanza, never a full verse.

If asked to add a fixture containing real lyrics, refuse and write synthetic text instead.

---

## 3. Storage namespacing

Rocola shares an origin with Molcajete on GitHub Pages. All IndexedDB
database names, Cache Storage keys, and localStorage key prefixes must
be rocola-prefixed. Never reuse a Molcajete storage identifier.

IndexedDB, Cache Storage and localStorage are scoped to the **origin**,
`https://stoneyboney.github.io`, not to the path. Service worker *scope* is
path-based and will look correct, which is exactly what makes this easy to
miss: two apps can have perfectly separated scopes and still be reading and
writing one database.

The identifiers this repository owns:

| Kind | Where | Value |
|---|---|---|
| IndexedDB database | `app/src/infra/db.ts` | `rocola` |
| Cache Storage prefix | `workbox.cacheId` in `app/vite.config.ts` | `rocola` |
| localStorage / sessionStorage | — | none exist; any added must be `rocola:`-prefixed |

`workbox.cacheId` is set explicitly and must stay that way. Without it,
workbox names its caches `workbox-precache-v2-<registration.scope>` — which
happens to differ between the two apps, but only as a side effect of a
library default. Add one `runtimeCaching` rule with an explicit `cacheName`
and that accident stops protecting anything.

`navigator.storage.persist()` is also origin-scoped and is deliberately
*not* namespaced: there is one persistence grant per origin and both apps
share it. That is nothing to fix.

---

## 4. Shared prep package

`molcajete-prep` is a **shared dependency**, pinned by version, consumed by both Molcajete and Rocola.

- Never fork, vendor, or copy code out of `molcajete-prep` into this repo.
- Fixes to glossing, lemmatisation, Wiktionary lookup, frequency ranking, or the teach-set core belong **upstream in `molcajete-prep`**, not here.
- Rocola-specific prep code (`lastfm/`, `lrclib/`, `matcher/`, `langfilter/`, `variety/`) stays here and must not leak Rocola concepts into the shared package.
- Bump the pin deliberately. Do not float the version.

---

## 5. Dialect handling

The `homeDialect` config value (default `es-MX`) governs all regional rendering. It is never hard-coded.

- `variety` defaults to `general`. Over-tagging is the expected model failure mode — when the gloss provider is uncertain, `general` wins.
- `homeEquivalent` is **null** when the home dialect uses the same word. Never populate it with a synonym for its own sake.
- Non-home-dialect forms are **recognition-only**. Never generate a German-front → Spanish-back production card for a sense whose `variety` is neither `general` nor `homeDialect`. This rule exists to stop the user producing Argentine vocabulary in Monterrey; it is not negotiable.
- The variety badge is visually subordinate to the gloss. It is context, not the answer.

---

## 6. Teach-set construction

- Frequency counting runs over **unique lines**, never the raw token stream. A repeated chorus must not inflate its own vocabulary. This is the single most important behavioural difference from Molcajete's builder.
- **Never split a song.** The 18-card cap is retained, but a song exceeding it is surfaced as "dense" for the user to decide about. Chapter-splitting logic is deleted, not disabled.
- One song = one session.

---

## 7. Coverage

- `coverageWarnThreshold` defaults to **0.95** (not Molcajete's 0.90).
- Coverage is a **diagnostic with a soft warning. It is never a gate.** Do not add any code path where low coverage blocks, hides, or locks the reader.

---

## 8. External API clients

**LRCLIB**

- Send a `User-Agent` identifying the app, name and version.
- Request plain lyrics. Discard synced.
- Cache hits *and* misses. Re-check misses monthly; never re-run the full lookup ladder on every pass.
- `instrumental: true` → terminal `no_lyrics`. Do not retry.
- Treat every field as optional. Never assume presence.

**last.fm**

- Read-only. API key in local config, **never committed**.
- Pace requests; do not parallelise aggressively.
- Skip the `nowplaying` entry in `getRecentTracks` — it has no timestamp and will reappear as a normal scrobble.

**General**

- Do not use undocumented or private endpoints of any streaming service. If an integration requires a scraped session cookie, it is out of bounds.
- Never add a lyrics provider that requires scraping. LRCLIB and manual paste are the only sources in v1.

---

## 9. Matching

- Normalisation is for **comparison only**. Always preserve and display the original scrobble strings.
- Parenthetical stripping is **stop-list driven**. Never strip a parenthetical unless its content matches a known qualifier — many real titles contain parentheses.
- Fuzzy matches scoring 0.70–0.85 go to a manual confirmation queue. **Never auto-accept a fuzzy match below 0.85.** A wrong lyric silently attached to a track is worse than no lyric.

---

## 10. Language filtering

- Classify on the **lyric text**, never on last.fm artist tags.
- Run the classifier locally. No cloud language-detection service.
- Tracks below the confidence threshold go to manual review, not to silent rejection.

---

## 11. Line notes

- **Manually authored only** in v1. Do not auto-generate cultural or idiomatic notes.
- A confidently wrong cultural note is worse than no note. If asked to add LLM generation for line notes, push back and reference this rule.

---

## 12. Gloss provider

- Ollama is the default. It must run without credentials so re-runs during tuning stay free.
- The provider returns **strict JSON** — no prose, no markdown fences, no preamble. Parse defensively and reject malformed responses rather than repairing them heuristically.
- `glossDe` is generated first. German quality degrades when the model translates from its own English output.
- Wiktionary supplies glosses; **Ollama is authoritative for `variety`, `register`, and `homeEquivalent`.**

---

## 13. Anki export

- Deck: `Spanisch::Rocola::[Artist]`
- Tags: `rocola` plus a per-track tag
- Note type: `Basic`, HTML on the back
- **Create the deck before calling `addNotes`.** Adding to a non-existent deck fails silently — this has bitten before.
- Tab-separated `.txt` with header directives is the reliable fallback path. AnkiConnect only works locally, from Claude Desktop or Claude Code on the same machine as Anki.

---

## 14. Working style

- **Plan before code.** Present the plan and wait for approval before writing implementation.
- Requirements come from the spec. When the spec is silent or ambiguous, ask rather than inventing.
- Prefer deleting dead inherited code over leaving it unreachable. EPUB ingest, chapter splitting, and the paragraph reader are deleted, not commented out.
