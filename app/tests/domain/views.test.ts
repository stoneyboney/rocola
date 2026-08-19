import { describe, expect, it } from 'vitest'
import { parseRoute, routeToHash, type Route } from '../../src/app/routes'
import type { LexiconEntry } from '../../src/domain/types'
import { buildGlossView } from '../../src/domain/view/glossView'

describe('buildGlossView', () => {
  const entry = (over: Partial<LexiconEntry> = {}): LexiconEntry => ({
    lemma: 'huizach',
    pos: 'NOUN',
    zipf: 1.2,
    bookCount: 1,
    firstChapter: 0,
    mexicanism: false,
    ...over,
  })

  it('reports a missing German gloss as null rather than an empty string', () => {
    // Wiktionary does not reach SPEC §12's 95% alone and the model half
    // rejects lemmas it doubts, so this is a normal state the sheet has to be
    // able to say out loud.
    const view = buildGlossView('m0037', entry())
    expect(view?.de).toBeNull()
    expect(view?.en).toBeNull()
    expect(view?.example).toBeNull()
  })

  it('carries the glosses and the book sentence when they are there', () => {
    const view = buildGlossView(
      'm0037',
      entry({
        de: 'die Akazie',
        en: 'acacia',
        example: { es: 'levantando polvo entre los huizaches.', chapterIndex: 0 },
      }),
    )
    expect(view?.de).toBe('die Akazie')
    expect(view?.en).toBe('acacia')
    expect(view?.example).toBe('levantando polvo entre los huizaches.')
  })

  it('passes a region note through whether or not the flag is set', () => {
    // The pipeline requires a note whenever `mexicanism` is true, but not the
    // reverse — `huizach` is annotated "Mexiko, ländlich" with the flag false.
    // Gating the note on the flag would drop that.
    //
    // SPEC §6.3 replaces this pair with `variety` and `register` in Phase 2,
    // and the same asymmetry will apply: a sense can carry a regional label
    // without its variety being anything but `general`.
    const unflagged = buildGlossView('m1', entry({ regionNote: 'Mexiko, ländlich' }))
    expect(unflagged?.regionNote).toBe('Mexiko, ländlich')
    expect(unflagged?.mexicanism).toBe(false)

    const flagged = buildGlossView(
      'm1',
      entry({ mexicanism: true, regionNote: 'MX, coloquial' }),
    )
    expect(flagged?.regionNote).toBe('MX, coloquial')
    expect(flagged?.mexicanism).toBe(true)
  })

  it('returns null for a key the lexicon slice does not hold', () => {
    expect(buildGlossView('m9999', undefined)).toBeNull()
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
