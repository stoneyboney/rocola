/**
 * Decodes and validates a built track, the second shape the import button
 * accepts.
 *
 * The mirror of what `scripts/build_track.py` writes. The two are maintained as
 * if by different people, because eventually one of them will be Swift.
 *
 * ## Why a version-1 file is rejected rather than partially read
 *
 * Version 1 carried lines as raw `text` with no tokens and no lexicon. It is
 * not a lesser version of this format; it is a file no reader can render — no
 * word is tappable and every `glossOnly` key points at nothing. Reading one
 * would produce a song that looks imported and does nothing when tapped, which
 * is worse than a refusal that says to rebuild.
 *
 * ## What is deliberately not read
 *
 * **`teach`.** The pipeline computes it against whatever known-set that desktop
 * had, which was already stale when the file was written — and the app has live
 * card and known state that the desktop cannot see. Sessions and coverage
 * recompute from the token counts. The field stays in the file as a CLI
 * diagnostic and there is a test asserting the app's answer differs from it.
 */

import type { Stanza, Track, TrackDocument } from '.'
import type { Lexicon, LexiconEntry, Register, Token, Variety } from '../types'

export const SUPPORTED_SCHEMA_VERSION = 2

const VARIETIES = new Set<string>([
  'general',
  'es-MX', 'es-AR', 'es-ES', 'es-CO', 'es-CL',
  'es-PE', 'es-VE', 'es-PR', 'es-DO', 'es-CU',
  'es-UY', 'es-EC', 'es-GT', 'es-BO', 'es-PY',
  'es-CR', 'es-PA', 'es-HN', 'es-SV', 'es-NI',
])

const REGISTERS = new Set<string>([
  'neutral', 'coloquial', 'vulgar', 'poetic', 'arcaic', 'albur',
])

export class TrackFormatError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'TrackFormatError'
  }
}

export class UnsupportedSchemaVersionError extends Error {
  constructor(
    readonly found: unknown,
    readonly supported: number = SUPPORTED_SCHEMA_VERSION,
  ) {
    super(`schemaVersion ${String(found)}, expected ${supported}`)
    this.name = 'UnsupportedSchemaVersionError'
  }
}

function object(value: unknown, at: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new TrackFormatError(`${at}: expected an object`)
  }
  return value as Record<string, unknown>
}

function str(value: unknown, at: string): string {
  if (typeof value !== 'string' || value === '') {
    throw new TrackFormatError(`${at}: expected a non-empty string`)
  }
  return value
}

function num(value: unknown, at: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new TrackFormatError(`${at}: expected a number`)
  }
  return value
}

function optionalString(value: unknown, at: string): string | undefined {
  if (value === undefined || value === null) return undefined
  return str(value, at)
}

/**
 * `{ k: v }` when `v` is set, and `{}` when it is not.
 *
 * `exactOptionalPropertyTypes` is on, so `{ repeatOf: undefined }` is not the
 * same thing as a missing `repeatOf` — the first is a promise that the key is
 * there holding nothing. Spreading is how an optional field stays optional.
 */
function optional<K extends string, V>(
  key: K,
  value: V | undefined,
): Record<K, V> | Record<string, never> {
  return value === undefined ? {} : ({ [key]: value } as Record<K, V>)
}

function variety(value: unknown): Variety {
  // Unknown is `general` rather than an error. CLAUDE.md §5: over-tagging is
  // the failure mode, so an unrecognised code becomes the untagged answer —
  // and a whole song should not fail to import because one lemma came back
  // with a code this build has not heard of.
  return typeof value === 'string' && VARIETIES.has(value)
    ? (value as Variety)
    : 'general'
}

function register(value: unknown): Register {
  return typeof value === 'string' && REGISTERS.has(value)
    ? (value as Register)
    : 'neutral'
}

function parseToken(value: unknown, at: string): Token {
  const raw = object(value, at)
  const s = raw.s
  if (typeof s !== 'string') {
    throw new TrackFormatError(`${at}.s: expected a string`)
  }
  if (raw.ws === true) return { s, ws: true }

  const token: Token = { s }
  if (raw.l !== undefined) token.l = str(raw.l, `${at}.l`)
  if (raw.p !== undefined) token.p = str(raw.p, `${at}.p`)
  if (raw.t !== undefined) token.t = str(raw.t, `${at}.t`)
  return token
}

function parseEntry(value: unknown, at: string): LexiconEntry {
  const raw = object(value, at)
  const example = raw.example === undefined || raw.example === null
    ? undefined
    : object(raw.example, `${at}.example`)

  return {
    lemma: str(raw.lemma, `${at}.lemma`),
    pos: str(raw.pos, `${at}.pos`),
    zipf: num(raw.zipf, `${at}.zipf`),
    uniqueLineCount: num(raw.uniqueLineCount, `${at}.uniqueLineCount`),
    variety: variety(raw.variety),
    register: register(raw.register),
    ...optional('de', optionalString(raw.de, `${at}.de`)),
    ...optional('en', optionalString(raw.en, `${at}.en`)),
    ...optional(
      'example',
      example
        ? {
            es: str(example.es, `${at}.example.es`),
            ...optional('de', optionalString(example.de, `${at}.example.de`)),
          }
        : undefined,
    ),
    ...optional(
      'homeEquivalent',
      optionalString(raw.homeEquivalent, `${at}.homeEquivalent`),
    ),
    ...optional(
      'homeEquivalentNote',
      optionalString(raw.homeEquivalentNote, `${at}.homeEquivalentNote`),
    ),
    ...optional('morphNote', optionalString(raw.morphNote, `${at}.morphNote`)),
    ...optional(
      'confidence',
      typeof raw.confidence === 'number' ? raw.confidence : undefined,
    ),
  }
}

function parseStanza(value: unknown, at: string): Stanza {
  const raw = object(value, at)
  const lines = raw.lines
  if (!Array.isArray(lines) || lines.length === 0) {
    throw new TrackFormatError(`${at}.lines: expected a non-empty array`)
  }

  return {
    index: num(raw.index, `${at}.index`),
    ...optional(
      'repeatOf',
      typeof raw.repeatOf === 'number' ? raw.repeatOf : undefined,
    ),
    lines: lines.map((line, i) => {
      const row = object(line, `${at}.lines[${i}]`)
      const tokens = row.tokens
      if (!Array.isArray(tokens)) {
        // The version-1 shape, reaching here only if schemaVersion lied.
        throw new TrackFormatError(
          `${at}.lines[${i}].tokens: missing — rebuild with the current pipeline`,
        )
      }
      return {
        index: num(row.index, `${at}.lines[${i}].index`),
        text: typeof row.text === 'string' ? row.text : '',
        ...optional(
          'repeatOf',
          typeof row.repeatOf === 'number' ? row.repeatOf : undefined,
        ),
        tokens: tokens.map((token, j) =>
          parseToken(token, `${at}.lines[${i}].tokens[${j}]`),
        ),
      }
    }),
  }
}

/** Parse an already-decoded JSON value into a track document. */
export function parseTrack(value: unknown): TrackDocument {
  const raw = object(value, 'track')

  if (raw.schemaVersion !== SUPPORTED_SCHEMA_VERSION) {
    throw new UnsupportedSchemaVersionError(raw.schemaVersion)
  }

  const stanzasRaw = raw.stanzas
  if (!Array.isArray(stanzasRaw) || stanzasRaw.length === 0) {
    throw new TrackFormatError('stanzas: expected a non-empty array')
  }

  const lexiconRaw = object(raw.lexicon, 'lexicon')
  const lexicon: Lexicon = {}
  for (const [key, entry] of Object.entries(lexiconRaw)) {
    lexicon[key] = parseEntry(entry, `lexicon.${key}`)
  }

  const counts = object(raw.counts ?? {}, 'counts')
  const track: Track = {
    id: str(raw.id, 'id'),
    title: str(raw.title, 'title'),
    artist: str(raw.artist, 'artist'),
    homeDialect: variety(raw.homeDialect),
    ...optional('language', optionalString(raw.language, 'language')),
    ...optional(
      'languageConfidence',
      typeof raw.languageConfidence === 'number'
        ? raw.languageConfidence
        : undefined,
    ),
    ...optional(
      'lrclibId',
      typeof raw.lrclibId === 'number' ? raw.lrclibId : undefined,
    ),
    source: raw.source === 'manual' ? 'manual' : 'lrclib',
    fetchedAt: typeof raw.fetchedAt === 'string' ? raw.fetchedAt : '',
    wordTokens: typeof counts.wordTokens === 'number' ? counts.wordTokens : 0,
    uniqueWordTokens:
      typeof counts.uniqueWordTokens === 'number' ? counts.uniqueWordTokens : 0,
    dense: raw.dense === true,
  }

  const stanzas = stanzasRaw.map((stanza, i) =>
    parseStanza(stanza, `stanzas[${i}]`),
  )

  const glossOnly = Array.isArray(raw.glossOnly)
    ? raw.glossOnly.filter((key): key is string => typeof key === 'string')
    : []

  // Every key a token points at must resolve, or the reader opens a gloss
  // sheet on nothing. This is the check that would have caught version 1.
  for (const stanza of stanzas) {
    for (const line of stanza.lines) {
      for (const token of line.tokens) {
        if (token.ws !== true && token.t !== undefined && !(token.t in lexicon)) {
          throw new TrackFormatError(
            `lexicon: no entry for ${token.t}, which a token points at`,
          )
        }
      }
    }
  }

  return { track, stanzas, lexicon, glossOnly }
}
