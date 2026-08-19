/**
 * The token model, as everything above it sees it.
 *
 * This was the `.molcajete.json` bundle contract; the bundle, the book and the
 * chapter are gone with the EPUB pipeline (SPEC §3). What is left is the part
 * that was never book-shaped: a run of tokens, a lexicon keyed by lemma, and
 * the rule for which tokens the reader lets you tap.
 *
 * Two clarifications carried over from the pipeline, both of which contradict a
 * casual reading of the schema:
 *
 * 1. `t` is a **string** lexicon key (`"m0118"`), not a number.
 * 2. **Not every token carries every field.** Whitespace has only `s` and `ws`.
 *    Punctuation and numerals have `s` and `p`. A proper noun has `s`, `l` and
 *    `p` but no `t`, because it gets no lexicon entry — which is also what makes
 *    proper nouns untappable in the reader for free.
 *
 * ## Names that are about to change
 *
 * `Paragraph` and `BookId` are inherited names for things Rocola calls
 * something else. A `Line` of lyrics is structurally a `Paragraph` of tokens and
 * a `trackId` is structurally a `BookId`, so both are kept verbatim through the
 * fork and renamed in Phase 3, when `Track` and `LyricDocument` (SPEC §6.1,
 * §6.2) exist to rename them *to*. Renaming them now would mean inventing the
 * Rocola data model in a commit whose job is to remove the Molcajete one.
 */

export type LemmaKey = string
export type BookId = string

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

export interface Paragraph {
  id: string
  tokens: Token[]
}

export interface Example {
  es: string
  de?: string
  chapterIndex?: number
}

export interface LexiconEntry {
  lemma: string
  pos: string
  zipf: number
  bookCount: number
  firstChapter: number
  mexicanism: boolean
  /**
   * Present only where the glossing pass found something. An absent `de` means
   * "no German gloss" and the reader has to say so out loud; the pipeline's
   * validator rejects an empty string precisely so that the two cannot be
   * confused here.
   */
  de?: string
  en?: string
  regionNote?: string
  example?: Example
}

export type Lexicon = Record<LemmaKey, LexiconEntry>

/** True for tokens the reader turns into a tappable span. */
export function isTappable(token: Token): token is WordToken & { t: LemmaKey } {
  return token.ws !== true && typeof (token as WordToken).t === 'string'
}
