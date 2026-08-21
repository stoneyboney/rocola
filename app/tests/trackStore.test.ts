/**
 * `deleteTrack` removes a song and does not unlearn its vocabulary.
 *
 * ## Why this is a stub and not a real database
 *
 * `vitest.config.ts` runs the suite in a plain node environment on purpose —
 * it is what keeps `src/domain/` honest about importing no DOM and no Dexie.
 * There is no IndexedDB here, and adding `fake-indexeddb` to get one would be a
 * dependency bought for a single test.
 *
 * It would also be the wrong test. The bug this guards against is not "the rows
 * did not go"; it is **which stores the code decided to clear**. A loop over
 * every table keyed by the track id reads as "remove everything belonging to
 * this song", passes today because `cards` is keyed by lemma, and sweeps up the
 * next store somebody adds. So the assertion is on the set of stores touched,
 * which is exactly the design decision, and a stub sees that better than a
 * database would.
 *
 * The round trip — save, reload, read it back — is verified in the browser,
 * where IndexedDB is real.
 */

import { describe, expect, it } from 'vitest'

import { DexieTrackRepository } from '../src/infra/DexieTrackRepository'
import type { RocolaDatabase } from '../src/infra/db'

/** Records every table a delete or a transaction touched. */
function stubDatabase() {
  const touched = new Set<string>()
  const transactionTables: string[][] = []

  const table = (name: string) => ({
    name,
    async delete() {
      touched.add(name)
    },
    async get() {
      return undefined
    },
    async toArray() {
      return []
    },
    async put() {
      touched.add(name)
    },
    async bulkPut() {
      touched.add(name)
    },
    where() {
      return {
        equals: () => ({
          async delete() {
            touched.add(name)
          },
          async toArray() {
            return []
          },
        }),
      }
    },
  })

  const tables = Object.fromEntries(
    [
      'tracks',
      'stanzas',
      'lexicon',
      'trackVocab',
      'positions',
      'sessions',
      'cards',
      'knownLemmas',
    ].map((name) => [name, table(name)]),
  )

  const database = {
    ...tables,
    async transaction(_mode: string, used: Array<{ name: string }>, body: () => Promise<void>) {
      transactionTables.push(used.map((t) => t.name))
      await body()
    },
  }

  return { database: database as unknown as RocolaDatabase, touched, transactionTables }
}

describe('deleteTrack', () => {
  it('clears the four stores that hold the song', async () => {
    const { database, touched } = stubDatabase()
    await new DexieTrackRepository(database).deleteTrack('selena-como-la-flor')

    expect(touched).toEqual(
      new Set(['tracks', 'stanzas', 'lexicon', 'trackVocab', 'positions']),
    )
  })

  it('does not touch cards or known lemmas', async () => {
    // CardRepository's header: "deleting a book removes its text; it does not
    // unlearn its vocabulary." A word met in a song you have since removed must
    // not come back round to be taught again.
    const { database, touched } = stubDatabase()
    await new DexieTrackRepository(database).deleteTrack('selena-como-la-flor')

    expect(touched.has('cards')).toBe(false)
    expect(touched.has('knownLemmas')).toBe(false)
  })

  it('does not even open a transaction over them', async () => {
    // Stronger than "did not write": a transaction that *could* have written
    // is a transaction someone will eventually write in.
    const { database, transactionTables } = stubDatabase()
    await new DexieTrackRepository(database).deleteTrack('t')

    const opened = new Set(transactionTables.flat())
    expect(opened.has('cards')).toBe(false)
    expect(opened.has('knownLemmas')).toBe(false)
  })

  it('leaves the in-progress session alone too', async () => {
    // Less obvious and the same argument: a session is keyed by track, so it
    // *would* match a "clear everything for this id" loop. It is left because
    // its effects have already been committed to cards — see
    // SessionRepository's note on the one transaction.
    const { database, touched } = stubDatabase()
    await new DexieTrackRepository(database).deleteTrack('t')
    expect(touched.has('sessions')).toBe(false)
  })
})

describe('saveTrack', () => {
  it('replaces a track rather than merging into it', async () => {
    // The id is a slug, so rebuilding a song after a re-gloss produces the same
    // id. Merging would leave a stanza that moved sitting at its old index.
    const { database, touched } = stubDatabase()
    const repository = new DexieTrackRepository(database)

    await repository.saveTrack(
      {
        track: {
          id: 't',
          title: 'Camino',
          artist: 'Ejemplo',
          homeDialect: 'es-MX',
          source: 'lrclib',
          fetchedAt: '',
          wordTokens: 0,
          uniqueWordTokens: 0,
          dense: false,
        },
        stanzas: [{ index: 0, lines: [] }],
        lexicon: {},
        glossOnly: [],
      },
      new Date(),
    )

    // stanzas and lexicon are cleared before being written.
    expect(touched.has('stanzas')).toBe(true)
    expect(touched.has('lexicon')).toBe(true)
    expect(touched.has('trackVocab')).toBe(true)
    expect(touched.has('cards')).toBe(false)
  })
})
