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
 *   sessions      one row per teaching session in progress, keyed by track
 *   cards         FSRS state, one row per lemma
 *   knownLemmas   "Ich kenne das", one row per lemma
 *
 * `cards` and `knownLemmas` carry no owning id at all, deliberately: a word
 * learned in one song must never be taught again in another. That absence is
 * the enforcement rather than a convention — see `CardRepository`.
 *
 * ## Why there is one version and not three
 *
 * Molcajete's schema reached `version(3)` by adding stores across three phases,
 * and its upgrade path has to stay because there are devices holding data
 * written under version 1. There is no such device here. A database named
 * `rocola` has never existed, so it has no history to migrate, and carrying the
 * inherited version chain would be three claims about upgrades that never
 * happened. The first schema Rocola ships is version 1.
 *
 * The `books`, `chapters`, `lexicon`, `positions` and `chapterVocab` stores are
 * gone with the EPUB pipeline (SPEC §3). The song equivalents arrive in Phase 3
 * with `Track` and `LyricDocument`, as version 2.
 */

import Dexie, { type Table } from 'dexie'
import type { LemmaId } from '../domain/lemma'
import type { TeachingSession } from '../domain/session/session'
import type { SrsCard } from '../domain/srs/scheduler'

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
  }
}

export const db = new RocolaDatabase()
