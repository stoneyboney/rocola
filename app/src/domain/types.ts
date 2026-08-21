/**
 * The token model, as everything above it sees it.
 *
 * This was the `.molcajete.json` bundle contract, and it is now the track
 * contract. The bundle, the book and the chapter are gone; what stayed is the
 * part that was never book-shaped: a run of tokens, a lexicon keyed by lemma,
 * and the rule for which tokens the reader lets you tap.
 *
 * Two clarifications carried over from the pipeline, both of which contradict a
 * casual reading of the schema:
 *
 * 1. `t` is a **string** lexicon key (`"m0118"`), not a number.
 * 2. **Not every token carries every field.** Whitespace has only `s` and `ws`.
 *    Punctuation and numerals have `s` and `p`. A proper noun has `s`, `l` and
 *    `p` but no `t`, because it gets no lexicon entry — which is also what
 *    makes proper nouns untappable in the reader for free.
 *
 * ## What `uniqueLineCount` counts, and what it does not
 *
 * Occurrences across the song's **unique** lines. A chorus sung five times
 * contributes its vocabulary once (SPEC §7.4), so this is the number the teach
 * set is ranked and thresholded by.
 *
 * It is deliberately *not* the number coverage uses. Coverage counts over every
 * line, because you read the chorus five times and knowing its words genuinely
 * does make the page readable. Same lexicon, two questions — see
 * `coverage.ts`, which is where both are computed and where the distinction is
 * enforced by naming rather than by memory.
 */

export type LemmaKey = string
export type TrackId = string

/** A whitespace run. Carries no lemma, no POS and no lexicon key. */
export interface WhitespaceToken {
  s: string
  ws: true
}

/**
 * Anything that is not whitespace. `l` is absent on punctuation and numerals;
 * `t` is absent whenever the token has no lexicon entry to point at.
 */
export interface WordToken {
  s: string
  l?: string
  p?: string
  t?: LemmaKey
  ws?: undefined
}

export type Token = WhitespaceToken | WordToken

/**
 * SPEC §6.3's variety. `general` is pan-Hispanic and is both the default and
 * the fallback for anything unrecognised — CLAUDE.md §5: over-tagging is the
 * expected failure, so when in doubt `general` wins.
 *
 * A string union rather than an enum, because it arrives as JSON and the domain
 * layer is a port target: an enum would be a Swift translation problem for no
 * gain.
 */
export type Variety =
  | 'general'
  | 'es-MX' | 'es-AR' | 'es-ES' | 'es-CO' | 'es-CL'
  | 'es-PE' | 'es-VE' | 'es-PR' | 'es-DO' | 'es-CU'
  | 'es-UY' | 'es-EC' | 'es-GT' | 'es-BO' | 'es-PY'
  | 'es-CR' | 'es-PA' | 'es-HN' | 'es-SV' | 'es-NI'

/** SPEC §6.3. `albur` is Mexican wordplay, which is why this is not a boolean. */
export type Register =
  | 'neutral' | 'coloquial' | 'vulgar' | 'poetic' | 'arcaic' | 'albur'

export interface LexiconEntry {
  lemma: string
  pos: string
  zipf: number
  /** Occurrences across **unique** lines. See the header. */
  uniqueLineCount: number
  /**
   * Present only where the glossing pass found something. An absent `de` means
   * "no German gloss" and the reader has to say so out loud; the pipeline's
   * validator rejects an empty string precisely so that the two cannot be
   * confused here.
   */
  de?: string
  en?: string
  /**
   * One line of the song, showing the word in use. §13 allows exactly one per
   * card and never a stanza.
   *
   * A bare string, not `{ es, de }`. Molcajete's shape carried an optional
   * German translation of the example sentence; nothing in Rocola's pipeline
   * produces one and every consumer already flattened it to `.es`. The two
   * sides disagreed about this until a real file met `parseTrack`.
   */
  example?: string

  // -- SPEC §6.3, the variety extension --------------------------------
  variety: Variety
  register: Register
  /**
   * What a speaker of the home dialect would say instead. Null whenever the
   * variety is `general` or the reader's own — there is no "instead" then, and
   * CLAUDE.md §5 forbids filling it with a synonym for its own sake.
   */
  homeEquivalent?: string
  homeEquivalentNote?: string
  /** §9.3: voseo and vosotros forms. Recognisable, never drilled. */
  morphNote?: string
  confidence?: number
}

export type Lexicon = Record<LemmaKey, LexiconEntry>

/** True for tokens the reader turns into a tappable span. */
export function isTappable(token: Token): token is WordToken & { t: LemmaKey } {
  return token.ws !== true && typeof (token as WordToken).t === 'string'
}

/**
 * SPEC §9.2's badge rule, in one place.
 *
 * No badge for `general`, and none for the reader's own dialect — in Monterrey
 * a Monterrey word is just a word. The home dialect is a parameter and never a
 * constant (CLAUDE.md §5), which is the whole reason this takes an argument
 * rather than reading one.
 */
export function badgeFor(
  variety: Variety,
  homeDialect: Variety,
): string | null {
  if (variety === 'general' || variety === homeDialect) return null
  return variety.replace(/^es-/, '')
}
