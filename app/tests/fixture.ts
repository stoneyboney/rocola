/**
 * A synthetic text, built in code.
 *
 * Molcajete's fixture was a real `.molcajete.json` its pipeline produced, read
 * off disk. That file is gone with the pipeline, and CLAUDE.md §2 would forbid
 * its replacement anyway: no lyric text in this repository, not in fixtures,
 * not anywhere. So the fixture is invented Spanish written for the test.
 *
 * It is deliberately tiny and deliberately hand-countable. Every assertion
 * against it should be checkable by reading this file, which the 26,829-byte
 * bundle it replaces was not.
 *
 * The shape is still `Paragraph[]` and a `Lexicon`, the names Phase 3 renames
 * to lines and stanzas once `LyricDocument` exists.
 */

import type { LemmaKey, LexiconEntry, Lexicon, Paragraph, Token } from '../src/domain/types'

export const space: Token = { s: ' ', ws: true }
export const punct = (s: string): Token => ({ s, p: 'PUNCT' })

export function word(surface: string, lemma: string, key: LemmaKey, pos = 'NOUN'): Token {
  return { s: surface, l: lemma, p: pos, t: key }
}

/** A name: it has a lemma but no lexicon key, so it is never taught. */
export function propn(surface: string, lemma = surface): Token {
  return { s: surface, l: lemma, p: 'PROPN' }
}

/** Builds a paragraph from tokens, interleaving the spaces. */
export function line(id: string, tokens: Token[]): Paragraph {
  const spaced: Token[] = []
  tokens.forEach((token, index) => {
    if (index > 0 && !(token.ws !== true && token.p === 'PUNCT')) spaced.push(space)
    spaced.push(token)
  })
  return { id, tokens: spaced }
}

export function entry(
  lemma: string,
  overrides: Partial<LexiconEntry> = {},
): LexiconEntry {
  return {
    lemma,
    pos: 'NOUN',
    zipf: 3.8,
    bookCount: 4,
    firstChapter: 0,
    mexicanism: false,
    de: `${lemma} auf Deutsch`,
    en: `${lemma} in English`,
    example: { es: `Una frase con ${lemma}.`, de: `Ein Satz mit ${lemma}.` },
    ...overrides,
  }
}

/**
 * Eight open-class words, three closed-class ones and a name.
 *
 * The closed-class entries carry a high zipf on purpose: they clear every
 * frequency threshold and would head the teach set if the part-of-speech rule
 * were not doing its job. That is the thing worth pinning.
 */
export const LEXICON: Lexicon = {
  k1: entry('cerro', { zipf: 3.4 }),
  k2: entry('sierra', { zipf: 3.6 }),
  k3: entry('caballo', { zipf: 4.1 }),
  k4: entry('sombra', { zipf: 4.0 }),
  k5: entry('camino', { zipf: 4.3 }),
  k6: entry('cantar', { pos: 'VERB', zipf: 4.2 }),
  k7: entry('luna', { zipf: 4.4 }),
  k8: entry('viejo', { pos: 'ADJ', zipf: 4.5 }),
  // Never taught, whatever their frequency. CLAUDE.md's closed-class rule.
  f1: entry('el', { pos: 'DET', zipf: 6.9 }),
  f2: entry('de', { pos: 'ADP', zipf: 6.8 }),
  f3: entry('y', { pos: 'CCONJ', zipf: 6.7 }),
}

export function lexiconMap(): Map<LemmaKey, LexiconEntry> {
  return new Map(Object.entries(LEXICON))
}

/**
 * Four lines. **17 word tokens**, of which 1 is a proper noun and 16 are keyed.
 *
 *   open-class    cerro sierra caballo sombra camino cantar luna viejo  = 8
 *   closed-class  el×4 de×3 y×1                                        = 8
 *   PROPN         Durango, no key, never taught, always covered         = 1
 *
 * Punctuation carries no lemma and is not a word token. Every number here is
 * countable by reading the four lines below.
 */
export function paragraphs(): Paragraph[] {
  return [
    line('p0', [
      word('El', 'el', 'f1', 'DET'),
      word('cerro', 'cerro', 'k1'),
      word('de', 'de', 'f2', 'ADP'),
      propn('Durango'),
      punct(','),
    ]),
    line('p1', [
      word('la', 'el', 'f1', 'DET'),
      word('sierra', 'sierra', 'k2'),
      word('y', 'y', 'f3', 'CCONJ'),
      word('el', 'el', 'f1', 'DET'),
      word('caballo', 'caballo', 'k3'),
      punct('.'),
    ]),
    line('p2', [
      word('Cantan', 'cantar', 'k6', 'VERB'),
      word('a', 'de', 'f2', 'ADP'),
      word('la', 'el', 'f1', 'DET'),
      word('luna', 'luna', 'k7'),
      punct(','),
    ]),
    line('p3', [
      word('sombra', 'sombra', 'k4'),
      word('del', 'de', 'f2', 'ADP'),
      word('camino', 'camino', 'k5'),
      word('viejo', 'viejo', 'k8', 'ADJ'),
      punct('.'),
    ]),
  ]
}
