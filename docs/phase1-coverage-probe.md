# Phase 1 — LRCLIB coverage probe

**Run 2026-08-19 against the real rotation. 254 tracks, two samples.**

SPEC §14 makes Phase 1 a measurement whose result changes the plan, and §15's
first open question sets the decision threshold: *"If LRCLIB hit rate on the
real rotation is below ~50%, manual paste becomes the primary path and the
matcher's priority drops sharply."*

It is not below 50%. **94% of the Spanish rotation resolved.**

Per-track tables live in the gitignored `reports/`; this file holds the
aggregates and what follows from them.

---

## The headline

| | tracks | resolved | es-confirmed |
|---|---:|---:|---:|
| **Sample 2** — Spanish-artist catalogue | 104 | 96 (92%) | 44 |
| ↳ **excluding Dover and Los Bitchos** | 52 | **49 (94%)** | 43 |
| **Sample 1** — what §7.1's heuristic selects | 150 | 104 (69%) | 14 (9%) |

Dover and Los Bitchos are excluded from the second row for cause, not
convenience: Dover is a Spanish band that sings in English (1 Spanish track of
49) and Los Bitchos are an instrumental cumbia group. Both are in the sample on
purpose — see *What the language filter caught* below.

**LRCLIB is viable as the primary path.** Manual paste (§8.5) stays as the
escape hatch it was specified as, not the main route.

---

## The finding that changes Phase 2

**The fuzzy layer resolved 3 tracks out of 254. It is over-engineering.**

| rung | | sample 1 | sample 2 |
|---|---|---:|---:|
| 1 | `/api/get` + album + duration | 72 (48%) | 78 (75%) |
| 2 | `/api/get`, loose | 30 (20%) | 18 (17%) |
| 3 | `/api/search` fielded, scored | 0 | 1 (1%) |
| 4 | `/api/search?q=`, scored | 2 (1%) | 0 |
| 5 | nothing matched | 46 (31%) | 7 (7%) |

The two exact rungs did **99%** of the work that got done. Rungs 3 and 4 —
the scoring, the weights, the thresholds, the manual-confirmation queue —
between them account for **1.2%** of the sample.

Two corollaries:

- **The manual confirmation queue was empty.** Zero tracks across 254 landed in
  §8.2's 0.70–0.85 band. The queue is a real safety mechanism and it should
  stay, but Phase 2 should not build UI for it: nothing has ever been in it.
- **Normalisation is not the bottleneck.** If it were, tracks would be falling
  through to the search rungs and being recovered there. They are not falling
  through at all — they resolve exactly, or they are genuinely absent.

`/api/get` matching on the §8.1-normalised strings is the whole system.

---

## What the misses actually are

Seven, in sample 2, and they are not a normalisation problem:

- **Chocolate Remix ×3** — Argentine underground reggaetón. Thin LRCLIB
  coverage, which is precisely the case SPEC §8.5's manual paste exists for.
- **Los Bitchos ×2** — an instrumental band. There are no lyrics to find.
  (A third of their tracks was correctly flagged `instrumental` by §8.4's
  terminal case rather than searched for.)
- **Dover ×2** — deep album tracks.

Sample 1's 31% miss rate is higher for the same structural reason in a
different key: German punk B-sides and small-label releases have thinner
coverage than a Selena catalogue that has been transcribed a thousand times.

---

## What the language filter caught

CLAUDE.md §10 forbids deciding language from artist metadata. The probe is the
argument for that rule rather than a restatement of it:

| | tracks | Spanish by the text |
|---|---:|---:|
| Dover — a **Spanish** band | 49 | **1** |
| Juanes — *Enter Sandman* | 1 | **0** |
| Shakira feat. Wyclef Jean | 1 | **0** |

Any artist-tag filter hands Dover's entire catalogue to a Spanish reader and
teaches them the vocabulary of *Devil Came to Me*. Classifying on the fetched
text catches all three, including a Metallica cover by a Colombian artist.

Selena is the mirror image: 25 tracks, 25 resolved, 21 Spanish — the four that
are not are her English-language recordings, correctly separated.

---

## The §8.2 hazard, measured

`token_set_ratio` returns 1.0 whenever one side's tokens nest inside the
other's. That is the documented behaviour of the algorithm §8.2 names, and it
means `Ven Conmigo` scores perfectly against the medley `Ven Conmigo /
Perdóname` — an auto-accept of the wrong recording, which is the silent
mismatch CLAUDE.md §9 calls worse than no lyric at all.

**Measured: 3 subset collisions in 254 tracks**, one of which (Dover — *Green*,
rung 3) scored exactly 0.85, the accept threshold.

Small, but not zero, and it lands on precisely the medleys this rotation
contains. Since the fuzzy rungs turn out to be nearly unused, the cheapest fix
is to drop rungs 3–4 rather than to re-tune the scorer — the hazard only exists
inside them.

---

## Open questions this leaves

1. **Should rungs 3 and 4 be deleted?** They cost two API calls per miss, carry
   the only known correctness hazard in the matcher, and resolved 1.2% of the
   sample. Deleting them would make every miss cheaper and remove the subset
   problem entirely. Not done here: §8.2 specifies the ladder, and this is a
   spec decision.

2. **§7.1's selection heuristic does not work on this account.** 83% of the
   12-month top tracks (822 of 995) are `Die drei ???`, a German audio drama
   scrobbled one row per chapter. Playcount ranking cannot find a Spanish
   rotation that is a few plays across many tracks. Sample 2 had to be seeded
   by artist to exist at all. Whether selection gains a not-music exclusion, a
   language pre-filter, or something else is a spec question.

3. **A Spanish-artist seed is not a selection strategy.** It worked for a probe
   because the answer was already known. Phase 2 needs a way to *discover*
   Spanish tracks, and the honest options are classifying after fetching
   everything (expensive) or a language hint at selection time (which §10
   constrains).

4. **Galician is unavailable.** lingua does not have it among its 75 languages,
   so §7.3's seven-language set is six. Galician will read as Portuguese and
   fall outside the Spanish subset — a miss rather than a false positive.

---

## Method notes

- **No lyric text was retained.** LRCLIB's three lyric-bearing fields —
  `plainLyrics`, `syncedLyrics` and the undocumented `lyricsfile` — are cut to
  one by an allowlist at the HTTP boundary. The surviving text lives as a local
  variable long enough to be line-counted and classified. The report holds
  counts; the cache has no column that could hold text (longest stored string
  across 238 rows: 46 characters, a title).
- **The §8.3 cache works.** A second full pass took 68 seconds against several
  minutes, because 53 cached misses skipped the four-rung ladder. Hits are
  re-fetched by design — the cache stores no text, so classification needs the
  body again.
- Sample 2 required paging `user.getTopTracks` six deep. At one page the seed
  found 36 tracks and 4 of its artists appeared to have no catalogue at all.
