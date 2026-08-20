/**
 * SPEC §6.1 and §6.2, as a built track actually arrives.
 *
 * The spec was written before the pipeline existed and describes a `Track` with
 * selection metadata and a seven-state lifecycle. Neither reaches the device,
 * and modelling them here would be modelling this app's own absence:
 *
 * - **`state: TrackState`** is a *pipeline* lifecycle — `candidate`,
 *   `no_lyrics`, `not_spanish`. A track that is on the device is `ready` by
 *   construction; the others describe tracks that never became a file.
 * - **`playcount30d` / `lastPlayedAt`** are §7.1's selection metadata, and
 *   selection is not built. Phase 1 measured why: 83% of the top tracks are an
 *   audio drama and playcount ranking cannot find the Spanish rotation.
 * - **`titleNorm` / `artistNorm`** belong to the matcher, for comparison only
 *   (CLAUDE.md §9). This app displays originals and never compares.
 * - **`id`** is a slug, not the spec's UUID. A UUID would make every rebuild of
 *   one song a new track; the slug *is* the identity, and re-importing after a
 *   re-gloss replaces rather than duplicates.
 *
 * ## Two views of one song, and the reader needs both
 *
 * `stanzas` holds every line in order, repeats included — that is what gets
 * rendered, because you read a chorus every time it comes round. `uniqueLines`
 * derives the other view, which is what the teach set counts over. Neither is
 * "the" lines; see `coverage.ts`.
 */

import type { Lexicon, LemmaKey, Token, TrackId, Variety } from './types'

/** SPEC §6.2's `Line`, plus the repeat marker the unique-line view needs. */
export interface Line {
  /** Global line index within the document. */
  index: number
  /** Raw, exactly as fetched. §10.1: never reflowed. */
  text: string
  tokens: Token[]
  /**
   * The index of the first line carrying this text, or absent if this is it.
   *
   * Not in SPEC §6.2, which marks repeats at stanza level only (§7.4 step 3).
   * It is here because `uniqueLines` is derived from it and because a chorus
   * can repeat without its whole stanza repeating.
   */
  repeatOf?: number
}

export interface Stanza {
  index: number
  lines: Line[]
  /** Set when this stanza duplicates an earlier one. §10.1 de-emphasises it. */
  repeatOf?: number
}

export interface Track {
  id: TrackId
  title: string
  artist: string
  /** The dialect every regional judgement in `lexicon` was made against. */
  homeDialect: Variety
  language?: string
  languageConfidence?: number
  lrclibId?: number
  source: 'lrclib' | 'manual'
  fetchedAt: string
  /** Word tokens across every line, and across unique lines. See coverage.ts. */
  wordTokens: number
  uniqueWordTokens: number
  /** §11.1: over the 18-card cap. Surfaced for the reader; never acted on. */
  dense: boolean
}

/** A track and everything needed to render it. What the reader is handed. */
export interface TrackDocument {
  track: Track
  stanzas: Stanza[]
  lexicon: Lexicon
  /** Underlined in the reader, never carded. */
  glossOnly: LemmaKey[]
}

/** Every line, in document order, repeats included. What gets rendered. */
export function linesOf(stanzas: readonly Stanza[]): Line[] {
  return stanzas.flatMap((stanza) => stanza.lines)
}

/**
 * First occurrence of each line, in document order. What the teach set counts.
 *
 * SPEC §7.4 step 2. A chorus sung five times contributes its vocabulary once —
 * otherwise the builder teaches the hook and skips the verses, which is exactly
 * backwards since the hook is the part repetition teaches you for free.
 */
export function uniqueLinesOf(stanzas: readonly Stanza[]): Line[] {
  return linesOf(stanzas).filter((line) => line.repeatOf === undefined)
}
