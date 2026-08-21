/**
 * The import path.
 *
 * `ImportButton` cannot narrow its `accept` past `.json` — iOS matches it
 * against the system's idea of a file's type — so the extension was never going
 * to be the discriminator anyway. The file is parsed once and dispatched on its
 * *shape*, which is what makes AirDrop's renaming harmless.
 *
 * Two shapes: an **array** is a `known.json` seed, an **object** is a built
 * track. Molcajete's object arm was a bundle; the shape survived the fork
 * empty and Phase 3 filled it, without touching the button, the screen, or
 * anything about how a file gets onto the device.
 */

import type { KnownLemmaRepository } from '../domain/ports/KnownLemmaRepository'
import type { TrackRepository } from '../domain/ports/TrackRepository'
import { parseKnownLemmas } from '../domain/seed/parseKnown'
import { parseTrack } from '../domain/track/parseTrack'

export type ImportOutcome =
  | {
      kind: 'known'
      /** Lemmas in the file, after normalising and deduplicating. */
      inFile: number
      /** How many of those the store did not already hold. */
      added: number
      total: number
    }
  | {
      kind: 'track'
      trackId: string
      title: string
      artist: string
      stanzas: number
      /** True when a track with this id was already stored and was replaced. */
      replaced: boolean
    }

export class UnrecognisedFileError extends Error {
  constructor() {
    super('neither a track nor a known.json')
    this.name = 'UnrecognisedFileError'
  }
}

export interface ImportTargets {
  known: KnownLemmaRepository
  tracks: TrackRepository
}

export async function importFile(
  file: File,
  targets: ImportTargets,
  now: Date = new Date(),
): Promise<ImportOutcome> {
  const text = await file.text()

  let value: unknown
  try {
    value = JSON.parse(text)
  } catch {
    throw new UnrecognisedFileError()
  }

  if (Array.isArray(value)) return importKnown(value, targets.known)
  if (typeof value === 'object' && value !== null) {
    return importTrack(value, targets.tracks, now)
  }
  throw new UnrecognisedFileError()
}

async function importTrack(
  value: unknown,
  tracks: TrackRepository,
  now: Date,
): Promise<ImportOutcome> {
  // Validated before a single row is written, so a rejected file leaves the
  // database exactly as it was.
  const document = parseTrack(value)

  const existing = await tracks.getTrack(document.track.id)
  await tracks.saveTrack(document, now)
  void requestPersistentStorage()

  return {
    kind: 'track',
    trackId: document.track.id,
    title: document.track.title,
    artist: document.track.artist,
    stanzas: document.stanzas.length,
    replaced: existing !== undefined,
  }
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
