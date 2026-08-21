/**
 * The song list, and the two numbers on each row.
 *
 * ## The two numbers come from different denominators
 *
 * **Cards to learn** is counted over *unique* lines: a chorus is one card
 * however often it is sung (§7.4). **Coverage** is measured over *every* line:
 * you read the chorus five times, and knowing its words makes the page readable
 * five times over (§11.2).
 *
 * They sit side by side on one row, which is exactly what makes them easy to
 * confuse. `TrackVocabulary` hands over `unique` and `all` as two named fields
 * so that picking one is a thing you have to do rather than a thing that
 * happens to you.
 *
 * ## Recomputed here, never read from the file
 *
 * A built track carries a `teach` array the pipeline computed against whatever
 * known-set that desktop had. It was stale when the file was written and the
 * app has live card and known state the desktop cannot see, so `parseTrack`
 * does not even carry it. Both numbers below are derived from the track's own
 * counts against the state as it is now.
 */

import { COVERAGE_WARNING_THRESHOLD, computeCoverage, type TrackVocabulary } from '../coverage'
import type { KnownState } from '../knownLemmas'
import type { TrackSummary } from '../ports/TrackRepository'
import { selectTeachSet } from '../teachSet'
import type { LemmaKey, LexiconEntry, TrackId } from '../types'

export interface TrackRow {
  id: TrackId
  title: string
  artist: string
  /** Counted over unique lines. Null when there is nothing left to learn. */
  cardsToLearn: number
  /** 0..1, measured over every line. */
  coverage: number
  /** Below SPEC §11.2's threshold. A warning, never a gate. */
  belowThreshold: boolean
  /** §11.1: more than the 18-card cap. Surfaced, never acted on. */
  dense: boolean
}

export interface TrackListView {
  rows: TrackRow[]
  isEmpty: boolean
}

export interface TrackListInput {
  summary: TrackSummary
  vocabulary: TrackVocabulary
  lexicon: ReadonlyMap<LemmaKey, LexiconEntry>
}

export function buildTrackRow(
  { summary, vocabulary, lexicon }: TrackListInput,
  state: KnownState,
): TrackRow {
  // `unique` — the teach set. A chorus counts once.
  const { teach } = selectTeachSet(
    vocabulary.unique.counts,
    lexicon,
    // A word with a card must not be taught again whether or not it has
    // matured. Known and carded are different tests and collapsing them
    // breaks one of them.
    new Set([...state.known, ...state.carded]),
  )

  // `all` — coverage. Every repeat of the chorus counts.
  const coverage = computeCoverage(vocabulary.all, lexicon, state.known)

  return {
    id: summary.id,
    title: summary.title,
    artist: summary.artist,
    cardsToLearn: teach.length,
    coverage,
    belowThreshold: coverage < COVERAGE_WARNING_THRESHOLD,
    dense: summary.dense,
  }
}

export function buildTrackListView(
  inputs: readonly TrackListInput[],
  state: KnownState,
): TrackListView {
  return {
    rows: inputs.map((input) => buildTrackRow(input, state)),
    isEmpty: inputs.length === 0,
  }
}
