/**
 * The import path dispatches on the file's *shape*, not its name.
 *
 * `ImportButton` cannot narrow its `accept` past `.json` — iOS matches it
 * against the system's idea of a file type and a double extension is not one —
 * so the extension was never available as a discriminator, and AirDrop renaming
 * a file has to stay harmless.
 *
 * Two shapes: an array is a `known.json`, an object is a built track. The
 * object arm was empty from the fork until Phase 3 filled it, and nothing about
 * the button or the screen changed when it did.
 */

import { describe, expect, it } from 'vitest'
import {
  importFile,
  UnrecognisedFileError,
  type ImportTargets,
} from '../src/app/importFile'
import { KnownFormatError } from '../src/domain/seed/parseKnown'
import { UnsupportedSchemaVersionError } from '../src/domain/track/parseTrack'
import { FakeKnownLemmaRepository, FakeTrackRepository } from './fakes'

function targets(): ImportTargets & {
  known: FakeKnownLemmaRepository
  tracks: FakeTrackRepository
} {
  return { known: new FakeKnownLemmaRepository(), tracks: new FakeTrackRepository() }
}

/** A `File` without a DOM: only `.text()` is ever called. */
function file(contents: string, name = 'whatever.json'): File {
  return { name, text: async () => contents } as unknown as File
}

describe('importing a known.json', () => {
  it('marks the lemmas known and counts what was new', async () => {
    const t = targets()
    const outcome = await importFile(file('["perro","casa","correr"]'), t)

    expect(outcome.kind).toBe('known')
    if (outcome.kind !== 'known') return
    expect(outcome.inFile).toBe(3)
    expect(outcome.added).toBe(3)
    expect(outcome.total).toBe(3)
    expect(await t.known.listAll()).toEqual(new Set(['casa', 'correr', 'perro']))
  })

  it('reports nothing new on a second import of the same seed', async () => {
    // §8 says the seed is re-runnable. It should say "0 new" rather than
    // claiming to have learned everything again.
    const t = targets()
    await importFile(file('["perro","casa"]'), t)
    const again = await importFile(file('["perro","casa"]'), t)

    expect(again.kind === 'known' && again.added).toBe(0)
    expect(again.kind === 'known' && again.inFile).toBe(2)
  })

  it('counts only the genuinely new lemmas when the deck has grown', async () => {
    const t = targets()
    await importFile(file('["perro"]'), t)
    const grown = await importFile(file('["perro","casa","sierra"]'), t)

    expect(grown.kind === 'known' && grown.added).toBe(2)
    expect(grown.kind === 'known' && grown.total).toBe(3)
  })

  it('rejects an array that is not lemma strings', async () => {
    await expect(importFile(file('[1,2,3]'), targets())).rejects.toThrow(
      KnownFormatError,
    )
  })

  it('does not care what the file is called', async () => {
    // The claim the header makes, and the reason the dispatch is on shape:
    // AirDrop renames files and iOS cannot narrow `accept` past `.json`.
    const t = targets()
    const outcome = await importFile(file('["perro"]', 'Unbenannt-3.json'), t)

    expect(outcome.kind).toBe('known')
  })

  it('writes nothing when the seed is rejected', async () => {
    const t = targets()
    await expect(importFile(file('["perro",7]'), t)).rejects.toThrow()

    expect(await t.known.listAll()).toEqual(new Set())
  })
})

describe('anything else', () => {
  it('is refused by shape rather than guessed at', async () => {
    // `{}` reaches the object arm now and is rejected there, by parseTrack,
    // rather than by the dispatch — which is the right place for it.
    for (const contents of ['not json at all', '"a string"', '42', 'null']) {
      await expect(importFile(file(contents), targets())).rejects.toThrow(
        UnrecognisedFileError,
      )
    }
  })
})

describe('importing a track', () => {
  const song = {
    schemaVersion: 2,
    id: 'ejemplo-camino',
    title: 'Camino',
    artist: 'Ejemplo',
    homeDialect: 'es-MX',
    source: 'lrclib',
    fetchedAt: '2026-08-21T00:00:00Z',
    stanzas: [
      {
        index: 0,
        lines: [
          {
            index: 0,
            text: 'Camino solo',
            tokens: [{ s: 'Camino', l: 'camino', p: 'NOUN', t: 'k1' }],
          },
        ],
      },
    ],
    lexicon: {
      k1: {
        lemma: 'camino',
        pos: 'NOUN',
        zipf: 4.3,
        uniqueLineCount: 1,
        variety: 'general',
        register: 'neutral',
      },
    },
    teach: ['k1'],
    glossOnly: [],
    counts: { wordTokens: 1, uniqueWordTokens: 1 },
    dense: false,
  }

  it('stores the song and reports what it did', async () => {
    const t = targets()
    const outcome = await importFile(file(JSON.stringify(song)), t)

    expect(outcome.kind).toBe('track')
    if (outcome.kind !== 'track') return
    expect(outcome.trackId).toBe('ejemplo-camino')
    expect(outcome.stanzas).toBe(1)
    expect(outcome.replaced).toBe(false)
    expect(await t.tracks.getTrack('ejemplo-camino')).toBeDefined()
  })

  it('reports a re-import as a replacement', async () => {
    // The id is a slug, so rebuilding after a re-gloss is the same song.
    const t = targets()
    await importFile(file(JSON.stringify(song)), t)
    const again = await importFile(file(JSON.stringify(song)), t)

    expect(again.kind === 'track' && again.replaced).toBe(true)
    expect(await t.tracks.listTracks()).toHaveLength(1)
  })

  it('counts the vocabulary both ways at import', async () => {
    const t = targets()
    await importFile(file(JSON.stringify(song)), t)
    const vocabulary = await t.tracks.getTrackVocabulary('ejemplo-camino')

    expect(vocabulary).toBeDefined()
    expect(vocabulary!.all).toBeDefined()
    expect(vocabulary!.unique).toBeDefined()
  })

  it('writes nothing when the song is rejected', async () => {
    const t = targets()
    const broken = { ...song, lexicon: {} }
    await expect(importFile(file(JSON.stringify(broken)), t)).rejects.toThrow()

    expect(await t.tracks.listTracks()).toEqual([])
  })

  it('refuses a version-1 file by version', async () => {
    const t = targets()
    await expect(
      importFile(file(JSON.stringify({ ...song, schemaVersion: 1 })), t),
    ).rejects.toThrow(UnsupportedSchemaVersionError)
    expect(await t.tracks.listTracks()).toEqual([])
  })

  it('does not care what the file is called', async () => {
    const t = targets()
    const outcome = await importFile(
      file(JSON.stringify(song), 'Unbenannt-7.json'),
      t,
    )
    expect(outcome.kind).toBe('track')
  })
})
