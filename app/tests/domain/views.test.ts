import { describe, expect, it } from 'vitest'
import { parseRoute, routeToHash, type Route } from '../../src/app/routes'
import type { LexiconEntry } from '../../src/domain/types'
import { buildGlossView } from '../../src/domain/view/glossView'

describe('buildGlossView', () => {
  const entry = (over: Partial<LexiconEntry> = {}): LexiconEntry => ({
    lemma: 'huizach',
    pos: 'NOUN',
    zipf: 1.2,
    uniqueLineCount: 1,
    variety: 'general',
    register: 'neutral',
    ...over,
  })

  it('reports a missing German gloss as null rather than an empty string', () => {
    // Wiktionary does not reach SPEC §12's 95% alone and the model half
    // rejects lemmas it doubts, so this is a normal state the sheet has to be
    // able to say out loud.
    const view = buildGlossView('m0037', entry(), 'es-MX')
    expect(view?.de).toBeNull()
    expect(view?.en).toBeNull()
    expect(view?.example).toBeNull()
  })

  it('carries the glosses and the song line when they are there', () => {
    const view = buildGlossView(
      'm0037',
      entry({
        de: 'die Akazie',
        en: 'acacia',
        example: 'levantando polvo entre los huizaches.',
      }),
      'es-MX',
    )
    expect(view?.de).toBe('die Akazie')
    expect(view?.en).toBe('acacia')
    expect(view?.example).toBe('levantando polvo entre los huizaches.')
  })

  it('carries a register even when the variety is general', () => {
    // The asymmetry SPEC §6.3 keeps from Molcajete's flag-and-note pair: a
    // sense can be marked in register without belonging to one country.
    // `pendejo` is the real case — vulgar across Latin America, and `general`.
    const view = buildGlossView(
      'm1',
      entry({ variety: 'general', register: 'vulgar' }),
      'es-MX',
    )
    expect(view?.variety).toBe('general')
    expect(view?.register).toBe('vulgar')
    expect(view?.badge).toBeNull()
  })

  it('badges a foreign variety and not the home one', () => {
    // SPEC §9.2's table. In Monterrey a Monterrey word is just a word.
    const foreign = buildGlossView('m1', entry({ variety: 'es-AR' }), 'es-MX')
    expect(foreign?.badge).toBe('AR')

    const home = buildGlossView('m1', entry({ variety: 'es-MX' }), 'es-MX')
    expect(home?.badge).toBeNull()
  })

  it('takes the home dialect as an argument, never a constant', () => {
    // CLAUDE.md §5. Move home and the same word changes how it is shown.
    const sameWord = entry({ variety: 'es-MX' })
    expect(buildGlossView('m1', sameWord, 'es-AR')?.badge).toBe('MX')
    expect(buildGlossView('m1', sameWord, 'es-MX')?.badge).toBeNull()
  })

  it('returns null for a key the lexicon slice does not hold', () => {
    expect(buildGlossView('m9999', undefined, 'es-MX')).toBeNull()
  })
})

describe('routes', () => {
  const cases: [string, Route][] = [
    ['', { name: 'home' }],
    ['#', { name: 'home' }],
    ['#/', { name: 'home' }],
    ['#/wiederholen', { name: 'review' }],
  ]

  it.each(cases)('parses %s', (hash, route) => {
    expect(parseRoute(hash)).toEqual(route)
  })

  it('round-trips', () => {
    for (const [, route] of cases) {
      expect(parseRoute(routeToHash(route))).toEqual(route)
    }
  })

  it('falls back to the home screen rather than a dead one', () => {
    // Including the book routes Molcajete used to answer. A home-screen icon
    // saved before the fork, or a bookmark, must not land on a blank page.
    for (const hash of [
      '#/book/anonimo-los-del-cerro',
      '#/book/anonimo-los-del-cerro/ch/2',
      '#/book/anonimo-los-del-cerro/ch/2/lernen',
      '#/nonsense',
      '#/wiederholen/2',
    ]) {
      expect(parseRoute(hash)).toEqual({ name: 'home' })
    }
  })
})
