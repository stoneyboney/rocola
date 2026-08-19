import { describe, expect, it } from 'vitest'
import { computeCoverage, countVocabulary } from '../../src/domain/coverage'
import { lemmaId } from '../../src/domain/lemma'
import type { LexiconEntry, Paragraph, Token } from '../../src/domain/types'
import { LEXICON, lexiconMap, paragraphs } from '../fixture'

/** One paragraph of the given tokens, exactly as handed in. */
function text(tokens: Token[]): Paragraph[] {
  return [{ id: 'p0', tokens }]
}

const word = (s: string, l: string, t: string): Token => ({ s, l, p: 'NOUN', t })
const propn = (s: string, l: string): Token => ({ s, l, p: 'PROPN' })
const space: Token = { s: ' ', ws: true }
const punct = (s: string): Token => ({ s, p: 'PUNCT' })

function entry(lemma: string): LexiconEntry {
  return {
    lemma,
    pos: 'NOUN',
    zipf: 3,
    bookCount: 5,
    firstChapter: 0,
    mexicanism: false,
  }
}

describe('countVocabulary', () => {
  it('counts words, and only words', () => {
    const vocabulary = countVocabulary(
      text([
        word('casa', 'casa', 'm1'),
        space,
        punct(','),
        space,
        word('casas', 'casa', 'm1'),
        space,
        word('perro', 'perro', 'm2'),
        punct('.'),
      ]),
    )

    expect(vocabulary.tokenCount).toBe(3)
    expect(vocabulary.counts.get('m1')).toBe(2)
    expect(vocabulary.counts.get('m2')).toBe(1)
    expect(vocabulary.propnTokens).toBe(0)
  })

  it('separates proper nouns out — they have a lemma but no key', () => {
    const vocabulary = countVocabulary(
      text([word('casa', 'casa', 'm1'), space, propn('Demetrio', 'demetrio')]),
    )

    expect(vocabulary.tokenCount).toBe(2)
    expect(vocabulary.propnTokens).toBe(1)
    expect(vocabulary.counts.size).toBe(1)
  })
})

describe('computeCoverage', () => {
  const lexicon = new Map([
    ['m1', entry('casa')],
    ['m2', entry('perro')],
  ])

  const vocabulary = countVocabulary(
    text([
      word('casa', 'casa', 'm1'),
      space,
      word('casa', 'casa', 'm1'),
      space,
      word('perro', 'perro', 'm2'),
      space,
      propn('Demetrio', 'demetrio'),
    ]),
  )

  it('counts a proper noun as covered', () => {
    // §5 skips PROPN entirely — no card, no gloss. Counting it unknown would
    // penalise a chapter for a decision the pipeline already made.
    expect(computeCoverage(vocabulary, lexicon, new Set())).toBeCloseTo(1 / 4)
  })

  it('rises as lemmas become known, by occurrence not by type', () => {
    // `casa` is one lemma but two tokens.
    expect(computeCoverage(vocabulary, lexicon, new Set(['casa']))).toBeCloseTo(3 / 4)
    expect(computeCoverage(vocabulary, lexicon, new Set(['perro']))).toBeCloseTo(2 / 4)
  })

  it('reaches 1 when everything is known', () => {
    const known = new Set(['casa', 'perro'])
    expect(computeCoverage(vocabulary, lexicon, known)).toBe(1)
  })

  it('projects what a pending session would buy', () => {
    // §5 Step 4's "known ∪ justTaught": the chapter list answers "what will
    // this be like after I study?", not only "what is it like now?".
    const now = computeCoverage(vocabulary, lexicon, new Set(['perro']))
    const after = computeCoverage(
      vocabulary,
      lexicon,
      new Set(['perro']),
      new Set(['casa']),
    )
    expect(now).toBeCloseTo(2 / 4)
    expect(after).toBe(1)
  })

  it('calls an empty chapter fully covered rather than dividing by zero', () => {
    expect(computeCoverage(countVocabulary([]), lexicon, new Set()))
      .toBe(1)
  })
})

describe('against the synthetic fixture', () => {
  const lexicon = lexiconMap()

  it('partitions every word token into keyed or proper noun', () => {
    // The measurement the denominator rests on. Countable by reading
    // tests/fixture.ts: 17 word tokens, 16 keyed, 1 name.
    const vocabulary = countVocabulary(paragraphs())
    const keyed = [...vocabulary.counts.values()].reduce((a, b) => a + b, 0)

    expect(vocabulary.tokenCount).toBe(17)
    expect(keyed).toBe(16)
    expect(vocabulary.propnTokens).toBe(1)
    expect(keyed + vocabulary.propnTokens).toBe(vocabulary.tokenCount)
  })

  it('starts low and reaches 1 when the whole lexicon is known', () => {
    const vocabulary = countVocabulary(paragraphs())
    const everything = new Set(Object.values(LEXICON).map(lemmaId))

    // Only Durango is free, and it is 1 token of 17.
    expect(computeCoverage(vocabulary, lexicon, new Set())).toBeCloseTo(1 / 17)
    expect(computeCoverage(vocabulary, lexicon, everything)).toBe(1)
  })

  it('is dominated by the words it will never teach', () => {
    // 8 of the 16 keyed tokens are el/de/y. Learning every open-class word in
    // the text reaches 9 of 17 — the ceiling the closed-class rule imposes,
    // and the reason SPEC §8's Anki seed exists.
    const vocabulary = countVocabulary(paragraphs())
    const openClass = new Set(
      Object.values(LEXICON)
        .filter((e) => !['DET', 'ADP', 'CCONJ'].includes(e.pos))
        .map(lemmaId),
    )

    expect(computeCoverage(vocabulary, lexicon, openClass)).toBeCloseTo(9 / 17)
  })
})
