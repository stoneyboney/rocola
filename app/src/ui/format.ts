/**
 * Every user-facing string in the app is German (CLAUDE.md). This is where the
 * German lives, together with the number formatting, so the domain view models
 * can stay language-neutral and port to Swift without dragging copy along.
 */

import { UnrecognisedFileError, type ImportOutcome } from '../app/importFile'
import { KnownFormatError } from '../domain/seed/parseKnown'
import {
  TrackFormatError,
  UnsupportedSchemaVersionError,
} from '../domain/track/parseTrack'
import { COVERAGE_WARNING_THRESHOLD } from '../domain/coverage'

const numbers = new Intl.NumberFormat('de-DE')

export function stanzas(value: number): string {
  return value === 1 ? '1 Strophe' : `${numbers.format(value)} Strophen`
}

export function lemmas(value: number): string {
  return `${numbers.format(value)} Lemmata`
}

export function percent(fraction: number): string {
  return `${Math.round(fraction * 100)} %`
}

export function cards(value: number): string {
  return value === 1 ? '1 Karte' : `${numbers.format(value)} Karten`
}

export function sessions(value: number): string {
  return value === 1 ? '1 Sitzung' : `${numbers.format(value)} Sitzungen`
}

/** A song's status chip. Null when there is nothing to learn. */
export function cardsToLearn(count: number): string | null {
  return count === 0 ? null : `${cards(count)} lernen`
}

/** SPEC §6.3's four FSRS buttons. */
export const GRADE_LABELS = {
  again: 'Nochmal',
  hard: 'Schwer',
  good: 'Gut',
  easy: 'Leicht',
} as const

/** The home screen's due chip. Null when nothing is due — no chip, no nagging. */
export function dueCards(count: number): string | null {
  return count === 0 ? null : `${cards(count)} fällig`
}

export function sessionProgress(answered: number, total: number): string {
  return `${numbers.format(answered)} von ${numbers.format(total)}`
}

/**
 * SPEC §11.2's soft warning, and nothing more than a warning — CLAUDE.md §7
 * forbids any path where a low figure blocks, hides or locks the reader. It
 * never appears next to a lock, because there is no lock.
 *
 * The threshold is imported rather than repeated. Molcajete's copy hard-coded
 * 0.9 next to a constant that also said 0.9, which is one place too many for a
 * number the spec expects to be tuned by feel.
 */
export function coverageNote(fraction: number): string | null {
  if (fraction >= COVERAGE_WARNING_THRESHOLD) return null
  if (fraction < 0.6) {
    return `Nur ${percent(fraction)} Abdeckung — dieses Lied ist im Moment sehr anspruchsvoll.`
  }
  return `${percent(fraction)} Abdeckung — dieses Lied fordert viel Wortschatz.`
}

export interface ImportFailure {
  headline: string
  detail: string
}

/** What an import actually did, once it worked. */
export function describeImportSuccess(outcome: ImportOutcome): string {
  if (outcome.kind === 'track') {
    const what = `„${outcome.title}" von ${outcome.artist}`
    return outcome.replaced
      ? `${what} ersetzt · ${stanzas(outcome.stanzas)}`
      : `${what} importiert · ${stanzas(outcome.stanzas)}`
  }
  if (outcome.added === 0) {
    // Re-importing the same seed. Worth saying out loud, or it looks broken.
    return `Nichts Neues — diese ${lemmas(outcome.inFile)} sind schon bekannt.`
  }
  return `${lemmas(outcome.added)} neu als bekannt markiert · ${numbers.format(outcome.total)} insgesamt`
}

/**
 * German for the user, the validator's own message underneath it. The technical
 * line stays in English and stays visible: when a file is rejected the next
 * step is on the desktop, in the pipeline, and the path that failed is the
 * thing worth knowing there.
 */
export function describeImportFailure(error: unknown): ImportFailure {
  if (error instanceof UnsupportedSchemaVersionError) {
    // Not a lesser version of the format — a file with no tokens and no
    // lexicon, which no reader can render. Saying "rebuild" is the whole
    // useful content of the message.
    return {
      headline: `Dieses Lied hat Schemaversion ${String(error.found)}. Diese App liest Version ${error.supported}.`,
      detail: 'Mit der aktuellen Pipeline neu bauen: scripts/build_track.py.',
    }
  }
  if (error instanceof TrackFormatError) {
    return {
      headline: 'Die Datei ist kein gültiges Lied.',
      detail: error.message,
    }
  }
  if (error instanceof UnrecognisedFileError) {
    return {
      headline: 'Diese Datei kennt die App nicht.',
      detail:
        'Erwartet wird ein Lied aus build_track.py oder ein known.json aus seed_known.py.',
    }
  }
  if (error instanceof KnownFormatError) {
    return {
      headline: 'Diese known.json ist nicht lesbar.',
      detail: error.message,
    }
  }
  return {
    headline: 'Import fehlgeschlagen.',
    detail: error instanceof Error ? error.message : String(error),
  }
}
