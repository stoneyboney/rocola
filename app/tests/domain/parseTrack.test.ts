/**
 * The track format, as the app decodes it.
 *
 * The load-bearing tests are the version-1 refusal and the unresolvable-key
 * check: between them they are why a song that imports is a song that renders.
 */

import { describe, expect, it } from 'vitest'

import {
  SUPPORTED_SCHEMA_VERSION,
  TrackFormatError,
  UnsupportedSchemaVersionError,
  parseTrack,
} from '../../src/domain/track/parseTrack'

/** A minimal valid track. Synthetic Spanish, per CLAUDE.md §2. */
function track(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schemaVersion: 2,
    id: 'ejemplo-camino',
    title: 'Camino',
    artist: 'Ejemplo',
    homeDialect: 'es-MX',
    language: 'es',
    languageConfidence: 0.99,
    lrclibId: 1,
    source: 'lrclib',
    fetchedAt: '2026-08-20T00:00:00Z',
    stanzas: [
      {
        index: 0,
        repeatOf: null,
        lines: [
          {
            index: 0,
            text: 'Camino solo',
            repeatOf: null,
            tokens: [
              { s: 'Camino', l: 'camino', p: 'NOUN', t: 'k1' },
              { s: ' ', ws: true },
              { s: 'solo', l: 'solo', p: 'ADJ', t: 'k2' },
            ],
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
        de: 'der Weg',
        en: 'path',
        variety: 'general',
        register: 'neutral',
      },
      k2: {
        lemma: 'solo',
        pos: 'ADJ',
        zipf: 4.9,
        uniqueLineCount: 1,
        variety: 'general',
        register: 'neutral',
      },
    },
    teach: ['k1'],
    glossOnly: ['k2'],
    counts: { wordTokens: 2, uniqueWordTokens: 2 },
    dense: false,
    ...overrides,
  }
}

describe('a well-formed track', () => {
  it('decodes into the shape the reader is handed', () => {
    const doc = parseTrack(track())
    expect(doc.track.id).toBe('ejemplo-camino')
    expect(doc.track.homeDialect).toBe('es-MX')
    expect(doc.stanzas).toHaveLength(1)
    expect(doc.stanzas[0]!.lines[0]!.tokens).toHaveLength(3)
    expect(doc.lexicon.k1!.de).toBe('der Weg')
    expect(doc.glossOnly).toEqual(['k2'])
  })

  it('keeps whitespace tokens whole', () => {
    const tokens = parseTrack(track()).stanzas[0]!.lines[0]!.tokens
    expect(tokens[1]).toEqual({ s: ' ', ws: true })
  })

  it('omits absent optionals rather than setting them undefined', () => {
    // `exactOptionalPropertyTypes` is on, and a key present holding nothing is
    // a different claim from a key that is not there.
    const entry = parseTrack(track()).lexicon.k2!
    expect('de' in entry).toBe(false)
    expect('homeEquivalent' in entry).toBe(false)
  })

  it('reads null repeatOf as absent', () => {
    const stanza = parseTrack(track()).stanzas[0]!
    expect(stanza.repeatOf).toBeUndefined()
    expect(stanza.lines[0]!.repeatOf).toBeUndefined()
  })
})

describe('the version-1 refusal', () => {
  it('rejects a version-1 file by version, before looking at it', () => {
    // Version 1 had no tokens and no lexicon. It is not a lesser version of
    // this format — it is a file no reader can render, and importing one
    // would produce a song that looks fine and does nothing when tapped.
    expect(() => parseTrack(track({ schemaVersion: 1 }))).toThrow(
      UnsupportedSchemaVersionError,
    )
  })

  it('names the version it found and the one it wants', () => {
    try {
      parseTrack(track({ schemaVersion: 1 }))
      expect.unreachable()
    } catch (error) {
      expect(error).toBeInstanceOf(UnsupportedSchemaVersionError)
      const typed = error as UnsupportedSchemaVersionError
      expect(typed.found).toBe(1)
      expect(typed.supported).toBe(SUPPORTED_SCHEMA_VERSION)
    }
  })

  it('rejects a line with no tokens even if the version lied', () => {
    const lying = track()
    const stanzas = lying.stanzas as Array<Record<string, unknown>>
    ;(stanzas[0]!.lines as Array<Record<string, unknown>>)[0] = {
      index: 0,
      text: 'Camino solo',
    }
    expect(() => parseTrack(lying)).toThrow(/tokens: missing/)
  })
})

describe('the lexicon has to answer for every token', () => {
  it('rejects a token pointing at a key that is not there', () => {
    // The check that would have caught version 1: a gloss sheet opening on
    // nothing is the failure this format exists to prevent.
    const broken = track()
    const stanzas = broken.stanzas as Array<Record<string, unknown>>
    const line = (stanzas[0]!.lines as Array<Record<string, unknown>>)[0]!
    ;(line.tokens as Array<Record<string, unknown>>)[0]!.t = 'k999'

    expect(() => parseTrack(broken)).toThrow(TrackFormatError)
    expect(() => parseTrack(broken)).toThrow(/k999/)
  })

  it('does not mind a lexicon entry no token points at', () => {
    // The reverse is fine: a glossOnly key can outlive its last occurrence
    // without anything being wrong.
    const extra = track()
    ;(extra.lexicon as Record<string, unknown>).k9 = {
      lemma: 'extra',
      pos: 'NOUN',
      zipf: 1,
      uniqueLineCount: 0,
      variety: 'general',
      register: 'neutral',
    }
    expect(() => parseTrack(extra)).not.toThrow()
  })
})

describe('tolerance where a strict reading would cost a song', () => {
  it('reads an unknown variety as general rather than failing', () => {
    // CLAUDE.md §5: over-tagging is the failure mode, so an unrecognised code
    // becomes the untagged answer. A whole song should not fail to import
    // because one lemma came back with a code this build has not heard of.
    const odd = track()
    ;(odd.lexicon as Record<string, Record<string, unknown>>).k1!.variety =
      'es-419'
    expect(parseTrack(odd).lexicon.k1!.variety).toBe('general')
  })

  it('reads an unknown register as neutral', () => {
    const odd = track()
    ;(odd.lexicon as Record<string, Record<string, unknown>>).k1!.register =
      'sarcastic'
    expect(parseTrack(odd).lexicon.k1!.register).toBe('neutral')
  })

  it('defaults a missing source to lrclib', () => {
    const doc = parseTrack(track({ source: undefined }))
    expect(doc.track.source).toBe('lrclib')
  })
})

describe('malformed input', () => {
  it.each([null, 42, 'a string', []])('rejects %s', (value) => {
    expect(() => parseTrack(value)).toThrow()
  })

  it('rejects a track with no stanzas', () => {
    expect(() => parseTrack(track({ stanzas: [] }))).toThrow(TrackFormatError)
  })

  it('rejects a track with no lexicon', () => {
    expect(() => parseTrack(track({ lexicon: undefined }))).toThrow(
      TrackFormatError,
    )
  })

  it('names the path that failed', () => {
    const broken = track()
    ;(broken.lexicon as Record<string, Record<string, unknown>>).k1!.zipf =
      'four'
    expect(() => parseTrack(broken)).toThrow(/lexicon\.k1\.zipf/)
  })
})

describe('what it deliberately does not read', () => {
  it('ignores the baked teach array', () => {
    // The pipeline computed it against a known-set already stale when the file
    // was written. The app recomputes from token counts against live state,
    // so the field is not even carried into the document.
    const doc = parseTrack(track({ teach: ['k1', 'k2', 'nonsense'] }))
    expect(doc).not.toHaveProperty('teach')
    expect(Object.keys(doc)).toEqual(['track', 'stanzas', 'lexicon', 'glossOnly'])
  })
})
