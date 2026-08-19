/**
 * The import path.
 *
 * `ImportButton` cannot narrow its `accept` past `.json` — iOS matches it
 * against the system's idea of a file's type — so the extension was never going
 * to be the discriminator anyway. The file is parsed once and dispatched on its
 * *shape*, which is what makes AirDrop's renaming harmless.
 *
 * Molcajete accepted two shapes here, an object being a bundle and an array
 * being a seed. The bundle is gone with the EPUB pipeline (SPEC §3), so only
 * the array remains — but the dispatch stays, because it is what lets Phase 3
 * add the song document as a second shape without touching the button, the
 * screen, or anything about how a file gets onto the device.
 */

import { parseKnownLemmas } from '../domain/bundle/parseKnown'
import type { KnownLemmaRepository } from '../domain/ports/KnownLemmaRepository'

export type ImportOutcome = {
  kind: 'known'
  /** Lemmas in the file, after normalising and deduplicating. */
  inFile: number
  /** How many of those the store did not already hold. */
  added: number
  total: number
}

export class UnrecognisedFileError extends Error {
  constructor() {
    super('not a known.json')
    this.name = 'UnrecognisedFileError'
  }
}

export interface ImportTargets {
  known: KnownLemmaRepository
}

export async function importFile(
  file: File,
  targets: ImportTargets,
): Promise<ImportOutcome> {
  const text = await file.text()

  let value: unknown
  try {
    value = JSON.parse(text)
  } catch {
    throw new UnrecognisedFileError()
  }

  if (Array.isArray(value)) return importKnown(value, targets.known)
  throw new UnrecognisedFileError()
}

async function importKnown(
  value: unknown,
  known: KnownLemmaRepository,
): Promise<ImportOutcome> {
  const lemmas = parseKnownLemmas(value)

  // Counted before writing, so re-importing the same seed reports "0 new"
  // rather than claiming to have learned everything again.
  const before = await known.listAll()
  const added = lemmas.filter((lemma) => !before.has(lemma)).length

  await known.add(lemmas)
  void requestPersistentStorage()

  return {
    kind: 'known',
    inFile: lemmas.length,
    added,
    total: before.size + added,
  }
}

/**
 * Ask the browser not to evict the database.
 *
 * Best-effort and deliberately unawaited: Safari decides on its own terms and a
 * refusal is not a reason to fail an import that has already succeeded.
 */
async function requestPersistentStorage(): Promise<void> {
  try {
    await navigator.storage?.persist?.()
  } catch {
    // Not available, or refused. Nothing to do about either.
  }
}
