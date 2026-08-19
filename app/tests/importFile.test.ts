/**
 * The import path dispatches on the file's *shape*, not its name.
 *
 * `ImportButton` cannot narrow its `accept` past `.json` — iOS matches it
 * against the system's idea of a file type and a double extension is not one —
 * so the extension was never available as a discriminator, and AirDrop renaming
 * a file has to stay harmless.
 *
 * One shape is accepted, where Molcajete took two. The bundle is gone with the
 * EPUB pipeline (SPEC §3) and the object arm now falls through to a refusal;
 * Phase 3 fills it with the song document.
 */

import { describe, expect, it } from 'vitest'
import {
  importFile,
  UnrecognisedFileError,
  type ImportTargets,
} from '../src/app/importFile'
import { KnownFormatError } from '../src/domain/bundle/parseKnown'
import { FakeKnownLemmaRepository } from './fakes'

function targets(): ImportTargets & { known: FakeKnownLemmaRepository } {
  return { known: new FakeKnownLemmaRepository() }
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
    // `{}` is in this list where Molcajete would have tried to parse it as a
    // bundle. The object arm is free again, which is what Phase 3 uses for the
    // song document — the button and this dispatch do not change.
    for (const contents of ['not json at all', '"a string"', '42', 'null', '{}']) {
      await expect(importFile(file(contents), targets())).rejects.toThrow(
        UnrecognisedFileError,
      )
    }
  })
})
