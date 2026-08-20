/**
 * Coverage: the share of a text you can read without a gloss.
 *
 * SPEC §11.2, and its insistence that this is a diagnostic and not a gate.
 * CLAUDE.md §7 is blunter — no code path may let a low figure block, hide or
 * lock the reader. It is a number shown to the reader, and nothing else.
 *
 * ## Ported from Molcajete rather than shared with it
 *
 * The rest of the language work is imported from `molcajete-prep`. This is not:
 * it never existed in Python, only in Molcajete's own domain layer, so it is
 * here as a copy that has already diverged — the threshold below is Rocola's,
 * not Molcajete's. If a bug is found in the arithmetic, it has to be fixed in
 * both places by hand, and that is the price of the fork.
 *
 * ## What the denominator is
 *
 * §5 writes `coverage = known tokens / totalTokens`, which read literally would
 * put whitespace and punctuation in the denominator — a third of every chapter,
 * all of it trivially "covered", inflating every figure by roughly 30 points and
 * making the warning threshold meaningless.
 *
 * The denominator is word tokens: the ones carrying a lemma. Measured across
 * every chapter of both books Molcajete built, that count partitioned cleanly:
 *
 *     tokenCount = tokens with a lexicon key + PROPN tokens
 *     32257      = 31654                     + 603
 *
 * so nothing new has to be stored to know it.
 *
 * ## Why proper nouns count as covered
 *
 * §5 skips `PROPN` entirely — no card, no gloss — which is the pipeline
 * asserting that a name needs no teaching. Counting those same tokens as
 * unknown would then penalise a chapter for a decision the pipeline already
 * made, and a book heavy with place names would look unreadable for a reason
 * that has nothing to do with vocabulary.
 *
 * ## Splitting counting from computing
 *
 * `countVocabulary` needs the text; `computeCoverage` does not. That split is
 * what let Molcajete's chapter list show a figure for five chapters without
 * deserialising 11 MB. A song is nowhere near that size, so the split earns
 * less here — but it is also what makes `computeCoverage` a pure walk over a
 * few hundred integers, which is worth keeping on its own.
 */

import { linesOf, uniqueLinesOf, type Line, type Stanza } from './track'
import { lemmaId, type LemmaId } from './lemma'
import type { LemmaKey, LexiconEntry, TrackId } from './types'

/** Everything about a text's vocabulary that does not need the text itself. */
export interface Vocabulary {
  /** Occurrences per lexicon key. Proper nouns are absent — they have no key. */
  counts: Map<LemmaKey, number>
  /** Tokens skipped as names. Covered without ever being taught. */
  propnTokens: number
  /** Word tokens in total. The coverage denominator. */
  tokenCount: number
}

export function countVocabulary(lines: readonly Line[]): Vocabulary {
  const counts = new Map<LemmaKey, number>()
  let propnTokens = 0
  let tokenCount = 0

  for (const line of lines) {
    for (const token of line.tokens) {
      if (token.ws === true) continue
      // A lemma is what makes a token a word. Punctuation and numerals carry a
      // POS but no lemma, and they are not vocabulary.
      if (token.l === undefined) continue

      tokenCount++
      if (token.t === undefined) {
        // No lexicon key, but it has a lemma: skipped as a proper noun.
        propnTokens++
        continue
      }
      counts.set(token.t, (counts.get(token.t) ?? 0) + 1)
    }
  }

  return { counts, propnTokens, tokenCount }
}

/**
 * The share of this text's words you can read without a gloss, 0..1.
 *
 * `justTaught` is "known ∪ justTaught": the lemmas a pending session would
 * teach, so a listing can answer "what will this be like *after* I study?"
 * rather than only "what is it like now".
 */
export function computeCoverage(
  vocabulary: Vocabulary,
  lexicon: ReadonlyMap<LemmaKey, LexiconEntry>,
  known: ReadonlySet<LemmaId>,
  justTaught: ReadonlySet<LemmaId> = new Set(),
): number {
  if (vocabulary.tokenCount === 0) return 1

  let covered = vocabulary.propnTokens

  for (const [key, count] of vocabulary.counts) {
    const entry = lexicon.get(key)
    if (!entry) continue
    const id = lemmaId(entry)
    if (known.has(id) || justTaught.has(id)) covered += count
  }

  return covered / vocabulary.tokenCount
}

/**
 * Both counts, named so a caller has to choose. See THE TWO DENOMINATORS.
 *
 * Cached per track because the song list wants a figure for every track
 * without reading every track's tokens, which is the same reason Molcajete
 * cached `chapterVocab`.
 */
export interface TrackVocabulary {
  trackId: TrackId
  /** Every line. Coverage's denominator. */
  all: Vocabulary
  /** First occurrence of each line. The teach set's denominator. */
  unique: Vocabulary
}

/** Count a song both ways at once. The only way `TrackVocabulary` is built. */
export function countTrack(
  trackId: TrackId,
  stanzas: readonly Stanza[],
): TrackVocabulary {
  return {
    trackId,
    all: countVocabulary(linesOf(stanzas)),
    unique: countVocabulary(uniqueLinesOf(stanzas)),
  }
}

/**
 * SPEC §11.2: warn below 0.95, never block.
 *
 * **0.95, where Molcajete's was 0.90.** Its 0.90 was calibrated on prose, where
 * the surrounding sentence carries a reader past a word they do not know. Songs
 * are far more elliptical — sparse syntax, ellipsis, deliberate ambiguity — so
 * there is less context to be carried by, and 0.90 in a song feels materially
 * worse than 0.90 in a chapter.
 *
 * The number is a guess made in advance and SPEC §11.2 says to revisit it after
 * roughly a dozen songs, against felt experience rather than argument.
 */
export const COVERAGE_WARNING_THRESHOLD = 0.95
