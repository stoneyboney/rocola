import { describe, expect, it } from 'vitest'
import { countVocabulary } from '../../src/domain/coverage'
import { lemmaId } from '../../src/domain/lemma'
import {
  CLOSED_CLASS_POS,
  DEFAULT_TEACH_SET_OPTIONS,
  isTeachable,
  selectTeachSet,
  toLemmaIds,
  type TeachSetOptions,
} from '../../src/domain/teachSet'
import type { LemmaKey, LexiconEntry } from '../../src/domain/types'
import { LEXICON, lexiconMap, lines } from '../fixture'

function entry(over: Partial<LexiconEntry> = {}): LexiconEntry {
  return {
    lemma: 'madriguera',
    pos: 'NOUN',
    zipf: 2.9,
    uniqueLineCount: 14,
    variety: 'general',
    register: 'neutral',
    ...over,
  }
}

function options(over: Partial<TeachSetOptions> = {}): TeachSetOptions {
  return { ...DEFAULT_TEACH_SET_OPTIONS, ...over }
}

function select(
  entries: Record<LemmaKey, LexiconEntry>,
  known: string[] = [],
  opts: Partial<TeachSetOptions> = {},
) {
  const lexicon = new Map(Object.entries(entries))
  const counts = new Map([...lexicon.keys()].map((key) => [key, 1]))
  return selectTeachSet(counts, lexicon, new Set(known), options(opts))
}

describe('the SPEC §5 rules, one at a time', () => {
  const base = { zipf: 0, uniqueLineCount: 0, variety: 'general' as const }

  it('teaches a word met three times — a card pays for itself', () => {
    expect(isTeachable(entry({ ...base, uniqueLineCount: 3 }), options())).toBe(true)
    expect(isTeachable(entry({ ...base, uniqueLineCount: 2 }), options())).toBe(false)
  })

  it('teaches a common word on zipf alone', () => {
    expect(isTeachable(entry({ ...base, zipf: 3.5 }), options())).toBe(true)
    expect(isTeachable(entry({ ...base, zipf: 3.49 }), options())).toBe(false)
  })

  it('teaches a regionalism on two occurrences — this is why you are here', () => {
    const mex = { ...base, variety: 'es-MX' as const }
    expect(isTeachable(entry({ ...mex, uniqueLineCount: 2 }), options())).toBe(true)
    expect(isTeachable(entry({ ...mex, uniqueLineCount: 1 }), options())).toBe(false)
    // Without the flag, two occurrences are not enough.
    expect(isTeachable(entry({ ...base, uniqueLineCount: 2 }), options())).toBe(false)
  })

  it('glosses everything else', () => {
    const { teach, glossOnly } = select({ m1: entry({ ...base, uniqueLineCount: 1 }) })
    expect(teach).toEqual([])
    expect(glossOnly).toEqual(['m1'])
  })
})

describe('proper nouns', () => {
  it('are skipped before the teach rules, not after', () => {
    // Read §5's table top-down and Demetrio — hundreds of occurrences, so
    // bookCount >= 3 fires first — earns a card. CLAUDE.md says otherwise.
    const demetrio = entry({ lemma: 'demetrio', pos: 'PROPN', uniqueLineCount: 400 })
    expect(isTeachable(demetrio, options())).toBe(false)
  })

  it('get no card and no gloss either', () => {
    const { teach, glossOnly } = select({
      m1: entry({ lemma: 'demetrio', pos: 'PROPN', uniqueLineCount: 400 }),
    })
    expect(teach).toEqual([])
    expect(glossOnly).toEqual([])
  })
})

describe('closed-class parts of speech', () => {
  // The measurement behind the rule: unmodified, §5 makes 16 of the first 18
  // cards of `las-noches-mejicanas` function words, because zipf >= 3.5 catches
  // every one and bookCount sorts them to the top of the session.
  const functionWords: Array<[string, string]> = [
    ['el', 'DET'],
    ['de', 'ADP'],
    ['él', 'PRON'],
    ['y', 'CCONJ'],
    ['que', 'SCONJ'],
    ['ser', 'AUX'],
  ]

  it.each(functionWords)('never teaches %s (%s)', (lemma, pos) => {
    const word = entry({ lemma, pos, zipf: 7.4, uniqueLineCount: 8691 })
    expect(isTeachable(word, options())).toBe(false)
  })

  it('still glosses them — the reader is unchanged', () => {
    const { teach, glossOnly } = select({
      m1: entry({ lemma: 'el', pos: 'DET', zipf: 7.45, uniqueLineCount: 8691 }),
    })
    expect(teach).toEqual([])
    expect(glossOnly).toEqual(['m1'])
  })

  it('keeps interjections teachable — ¡órale! is the point of the app', () => {
    expect(CLOSED_CLASS_POS.has('INTJ')).toBe(false)
    const orale = entry({ lemma: 'órale', pos: 'INTJ', uniqueLineCount: 4 })
    expect(isTeachable(orale, options())).toBe(true)
  })
})

describe('ordering', () => {
  it('puts the most useful words first, so a partial session still helps', () => {
    const { teach } = select({
      m1: entry({ lemma: 'raro', uniqueLineCount: 3 }),
      m2: entry({ lemma: 'casa', uniqueLineCount: 90 }),
      m3: entry({ lemma: 'perro', uniqueLineCount: 12 }),
    })
    expect(teach).toEqual(['m2', 'm3', 'm1'])
  })

  it('breaks ties on the key, so two runs agree', () => {
    const { teach } = select({
      m9: entry({ lemma: 'nueve', uniqueLineCount: 5 }),
      m1: entry({ lemma: 'eins', uniqueLineCount: 5 }),
    })
    expect(teach).toEqual(['m1', 'm9'])
  })
})

describe('what you already know', () => {
  it('is not taught and is not underlined', () => {
    const { teach, glossOnly } = select(
      { m1: entry({ lemma: 'madriguera' }) },
      ['madriguera'],
    )
    expect(teach).toEqual([])
    expect(glossOnly).toEqual([])
  })

  it('matches on the bare lemma however the entry is keyed', () => {
    // `estar` is in the real lexicon twice, as AUX and as VERB, under two
    // different keys. Learning the word settles both.
    const { teach } = select(
      {
        m3589: entry({ lemma: 'estar', pos: 'VERB', uniqueLineCount: 76 }),
        m3590: entry({ lemma: 'Estar ', pos: 'VERB', uniqueLineCount: 76 }),
      },
      ['estar'],
    )
    expect(teach).toEqual([])
  })
})

describe('a word that already has a card', () => {
  it('is not taught again, even though it is not yet known', () => {
    const { teach, glossOnly } = select({ m1: entry({ lemma: 'madriguera' }) }, [], {
      carded: new Set(['madriguera']),
    })
    // Not taught: you are already learning it. Not underlined either: you have
    // seen it introduced.
    expect(teach).toEqual([])
    expect(glossOnly).toEqual([])
  })
})

describe('cards are global, not per book', () => {
  it('never teaches in book B a word that was learned in book A', () => {
    // The two books key the same Spanish word differently, which is exactly the
    // trap: `m0031` means nothing outside its own bundle.
    const bookA = new Map([['m0031', entry({ lemma: 'madriguera' })]])
    const bookB = new Map([['m0777', entry({ lemma: 'madriguera' })]])

    const learnedInA = new Set(toLemmaIds(['m0031'], bookA))
    expect(learnedInA).toEqual(new Set(['madriguera']))

    const { teach } = selectTeachSet(
      new Map([['m0777', 4]]),
      bookB,
      learnedInA,
      options(),
    )
    expect(teach).toEqual([])
  })
})

describe('against the synthetic fixture', () => {
  const lexicon = lexiconMap()

  function recompute(known: string[] = []) {
    const vocabulary = countVocabulary(lines())
    return selectTeachSet(vocabulary.counts, lexicon, new Set(known), options())
  }

  it('teaches the open-class words and nothing else', () => {
    const { teach } = recompute()
    const lemmas = teach.map((key) => lexicon.get(key)!.lemma).sort()

    expect(lemmas).toEqual([
      'caballo',
      'camino',
      'cantar',
      'cerro',
      'luna',
      'sierra',
      'sombra',
      'viejo',
    ])
  })

  it('teaches no closed-class word, however common it is', () => {
    // el, de and y sit at zipf 6.7–6.9 in the fixture, clearing every
    // frequency threshold there is. The part-of-speech rule is the only thing
    // keeping them out, which is exactly why it is pinned here.
    const { teach } = recompute()
    const lemmas = teach.map((key) => lexicon.get(key)!.lemma)

    expect(lemmas).not.toContain('el')
    expect(lemmas).not.toContain('de')
    expect(lemmas).not.toContain('y')

    for (const key of teach) {
      expect(CLOSED_CLASS_POS.has(lexicon.get(key)!.pos)).toBe(false)
    }
  })

  it('teaches no proper noun, because a name has no lexicon key at all', () => {
    const vocabulary = countVocabulary(lines())
    expect(vocabulary.propnTokens).toBe(1)
    for (const key of recompute().teach) {
      expect(lexicon.get(key)!.pos).not.toBe('PROPN')
    }
  })

  it('shrinks as words become known', () => {
    const before = recompute().teach.length
    const learned = toLemmaIds(recompute().teach.slice(0, 3), lexicon)
    const after = recompute(learned).teach.length

    expect(before).toBe(8)
    expect(after).toBe(5)
  })

  it('leaves nothing to teach once every lemma is known', () => {
    const everything = Object.values(LEXICON).map(lemmaId)
    const { teach, glossOnly } = recompute(everything)
    expect(teach).toEqual([])
    expect(glossOnly).toEqual([])
  })
})
