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
 * The shape is `Stanza[]` of `Line[]` and a `Lexicon` — SPEC §6.2, which is
 * what the reader and the teach set read from opposite ends.
 */

import type { Line, Stanza } from '../src/domain/track'
import type { LemmaKey, LexiconEntry, Lexicon, Token } from '../src/domain/types'

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
export function line(index: number, text: string, tokens: Token[]): Line {
  const spaced: Token[] = []
  tokens.forEach((token, i) => {
    if (i > 0 && !(token.ws !== true && token.p === 'PUNCT')) spaced.push(space)
    spaced.push(token)
  })
  return { index, text, tokens: spaced }
}

export function entry(
  lemma: string,
  overrides: Partial<LexiconEntry> = {},
): LexiconEntry {
  return {
    lemma,
    pos: 'NOUN',
    zipf: 3.8,
    uniqueLineCount: 4,
    variety: 'general',
    register: 'neutral',
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
export function lines(): Line[] {
  return [
    line(0, 'El cerro de Durango,', [
      word('El', 'el', 'f1', 'DET'),
      word('cerro', 'cerro', 'k1'),
      word('de', 'de', 'f2', 'ADP'),
      propn('Durango'),
      punct(','),
    ]),
    line(1, 'la sierra y el caballo.', [
      word('la', 'el', 'f1', 'DET'),
      word('sierra', 'sierra', 'k2'),
      word('y', 'y', 'f3', 'CCONJ'),
      word('el', 'el', 'f1', 'DET'),
      word('caballo', 'caballo', 'k3'),
      punct('.'),
    ]),
    line(2, 'Cantan a la luna,', [
      word('Cantan', 'cantar', 'k6', 'VERB'),
      word('a', 'de', 'f2', 'ADP'),
      word('la', 'el', 'f1', 'DET'),
      word('luna', 'luna', 'k7'),
      punct(','),
    ]),
    line(3, 'sombra del camino viejo.', [
      word('sombra', 'sombra', 'k4'),
      word('del', 'de', 'f2', 'ADP'),
      word('camino', 'camino', 'k5'),
      word('viejo', 'viejo', 'k8', 'ADJ'),
      punct('.'),
    ]),
  ]
}


/** The four lines as two stanzas. What the reader is handed. */
export function stanzas(): Stanza[] {
  const all = lines()
  return [
    { index: 0, lines: [all[0]!, all[1]!] },
    { index: 1, lines: [all[2]!, all[3]!] },
  ]
}

/**
 * The same song with its second stanza sung `times` times over.
 *
 * The repeats carry `repeatOf`, so `uniqueLinesOf` drops them and `linesOf`
 * keeps them — which is the entire two-denominator question in one fixture.
 */
export function withRepeatedStanza(times: number): Stanza[] {
  const [first, chorus] = stanzas()
  const out: Stanza[] = [first!, chorus!]
  for (let n = 1; n < times; n++) {
    out.push({
      index: out.length,
      repeatOf: chorus!.index,
      lines: chorus!.lines.map((line, i) => ({
        ...line,
        index: 4 + (n - 1) * 2 + i,
        repeatOf: line.index,
      })),
    })
  }
  return out
}
