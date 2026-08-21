/**
 * The IndexedDB schema. The only file in the app that knows Dexie exists,
 * together with the three repositories next to it (CLAUDE.md rule 4, inherited
 * from Molcajete).
 *
 * ## The database name is load-bearing
 *
 * `rocola`, and it must never be `molcajete`. Both apps are served from
 * `stoneyboney.github.io`, and IndexedDB is scoped to the **origin**, not to the
 * path — two Dexie instances opened under one name on one origin are one
 * database, with one set of object stores and two schemas fighting over the
 * version number. The service worker's scope *is* path-based and looks correct,
 * which is exactly what makes this easy to miss. CLAUDE.md §3.
 *
 * ## What is stored
 *
 *   tracks        one row per song — everything the song list draws
 *   stanzas       one row per stanza, read for one track at a time
 *   lexicon       one row per entry, the reader's bulk read
 *   trackVocab    both vocabulary counts, computed once at import
 *   positions     where you were in a song
 *   sessions      one row per teaching session in progress, keyed by track
 *   cards         FSRS state, one row per lemma
 *   knownLemmas   "Ich kenne das", one row per lemma
 *
 * `cards` and `knownLemmas` carry no owning id at all, deliberately: a word
 * learned in one song must never be taught again in another. That absence is
 * the enforcement rather than a convention — see `CardRepository`.
 *
 * ## Why version 2 is a second block and not an edit to version 1
 *
 * There is still no device holding version-1 data, so an edit would produce the
 * same result today. It is a second block anyway: a schema's version chain is a
 * record of what shipped, and rewriting it to look like the current shape was
 * always the shape is a small lie that costs nothing to avoid. There is no
 * upgrade function because every new store starts empty.
 *
 * ## Where the counts are a plain object and not a Map
 *
 * `TrackVocabularyRow` stores `counts` as `Record<LemmaKey, number>` where the
 * domain layer uses a `Map`. Molcajete's note, kept: a plain object
 * structured-clones without surprises on older Safari. `DexieTrackRepository`
 * converts at the boundary so nothing above it sees the difference.
 */

import Dexie, { type Table } from 'dexie'
import type { LemmaId } from '../domain/lemma'
import type { TeachingSession } from '../domain/session/session'
import type { SrsCard } from '../domain/srs/scheduler'
import type { Line, Track } from '../domain/track'
import type { LemmaKey, LexiconEntry, TrackId } from '../domain/types'

export interface TrackRow extends Track {
  importedAt: Date
}

export interface StanzaRow {
  trackId: TrackId
  index: number
  repeatOf?: number
  lines: Line[]
}

export interface LexiconRow {
  trackId: TrackId
  key: LemmaKey
  entry: LexiconEntry
}

/** As stored: a plain object, per the header. */
export interface StoredVocabulary {
  counts: Record<LemmaKey, number>
  propnTokens: number
  tokenCount: number
}

/**
 * **Both** counts, and that is the point of the row.
 *
 * `all` is coverage's denominator and `unique` is the teach set's. A row
 * holding one of them would make `TrackVocabulary` a comment and let a screen
 * pick a denominator without anybody choosing.
 */
export interface TrackVocabularyRow {
  trackId: TrackId
  all: StoredVocabulary
  unique: StoredVocabulary
}

export interface PositionRow {
  trackId: TrackId
  /** A line index, not pixels: it survives a type-size change. */
  lineIndex: number
  updatedAt: Date
}

export interface SessionRow {
  trackId: string
  session: TeachingSession
}

/** No owning id. See the header — that absence is the point. */
export interface CardRow {
  lemmaId: LemmaId
  card: SrsCard
}

/** No owning id here either. */
export interface KnownLemmaRow {
  lemmaId: LemmaId
  markedAt: Date
}

export class RocolaDatabase extends Dexie {
  tracks!: Table<TrackRow, string>
  stanzas!: Table<StanzaRow, [string, number]>
  lexicon!: Table<LexiconRow, [string, string]>
  trackVocab!: Table<TrackVocabularyRow, string>
  positions!: Table<PositionRow, string>
  sessions!: Table<SessionRow, string>
  cards!: Table<CardRow, string>
  knownLemmas!: Table<KnownLemmaRow, string>

  constructor(name = 'rocola') {
    super(name)
    // The `card.fsrs.due` index is what makes "what is due?" a range query
    // rather than a full scan. The key path reaches into the stored FSRS
    // object, which is where `due` lives and where it has to stay — CLAUDE.md
    // requires the whole card object be stored, never a copy of one field
    // beside it, because partial state cannot be rescheduled.
    this.version(1).stores({
      sessions: 'trackId',
      cards: 'lemmaId, card.fsrs.due',
      knownLemmas: 'lemmaId',
    })

    // Phase 3. Songs. No upgrade function: every store here starts empty, and
    // the compound keys put the track id in every one of them so that removing
    // a song is a handful of range deletes — and so that there is no way to
    // read one song's stanzas beside another song's lexicon.
    this.version(2).stores({
      tracks: 'id',
      stanzas: '[trackId+index], trackId',
      lexicon: '[trackId+key], trackId',
      trackVocab: 'trackId',
      positions: 'trackId',
    })
  }
}

export const db = new RocolaDatabase()
