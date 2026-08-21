/**
 * In-memory implementations of the ports.
 *
 * They exist so the teaching flow can be exercised end to end — select a teach
 * set, run a session, commit the effects, look again — without IndexedDB and
 * without adding a dependency. They implement the same interfaces the Dexie
 * classes do, so a divergence between them is a type error rather than a
 * surprise on the device.
 *
 * `FakeBookRepository` is gone with `BookRepository` (SPEC §3). The song
 * equivalent arrives in Phase 3 with `Track`; until then a test that needs a
 * text uses `tests/fixture.ts` directly.
 */

import { countTrack, type TrackVocabulary } from '../src/domain/coverage'
import type { LemmaId } from '../src/domain/lemma'
import type {
  TrackRepository,
  TrackSummary,
} from '../src/domain/ports/TrackRepository'
import type { Stanza, Track, TrackDocument } from '../src/domain/track'
import type { LemmaKey, LexiconEntry } from '../src/domain/types'
import type { CardRepository } from '../src/domain/ports/CardRepository'
import type { KnownLemmaRepository } from '../src/domain/ports/KnownLemmaRepository'
import type { SessionRepository } from '../src/domain/ports/SessionRepository'
import type { SessionEffect, TeachingSession } from '../src/domain/session/session'
import type { SrsCard } from '../src/domain/srs/scheduler'
import type { TrackId } from '../src/domain/types'

export class FakeCardRepository implements CardRepository {
  readonly rows = new Map<LemmaId, SrsCard>()

  async get(lemmaId: LemmaId): Promise<SrsCard | undefined> {
    return this.rows.get(lemmaId)
  }

  async getMany(lemmaIds: readonly LemmaId[]): Promise<Map<LemmaId, SrsCard>> {
    const found = new Map<LemmaId, SrsCard>()
    for (const id of lemmaIds) {
      const card = this.rows.get(id)
      if (card) found.set(id, card)
    }
    return found
  }

  async listCardedLemmas(): Promise<Set<LemmaId>> {
    return new Set(this.rows.keys())
  }

  async listDue(now: Date, limit?: number): Promise<SrsCard[]> {
    const due = [...this.rows.values()]
      .filter((card) => card.fsrs.due.getTime() <= now.getTime())
      .sort((a, b) => a.fsrs.due.getTime() - b.fsrs.due.getTime())
    return limit === undefined ? due : due.slice(0, limit)
  }

  async countDue(now: Date): Promise<number> {
    return (await this.listDue(now)).length
  }

  async put(card: SrsCard): Promise<void> {
    this.rows.set(card.lemmaId, card)
  }
}

export class FakeKnownLemmaRepository implements KnownLemmaRepository {
  readonly rows = new Set<LemmaId>()

  async listAll(): Promise<Set<LemmaId>> {
    return new Set(this.rows)
  }

  async add(lemmaIds: readonly LemmaId[]): Promise<void> {
    for (const id of lemmaIds) this.rows.add(id)
  }
}

/**
 * Mirrors `DexieSessionRepository.commit`, including the part that matters:
 * the session and its effects land together, and a completed session is
 * removed rather than kept.
 */
export class FakeSessionRepository implements SessionRepository {
  private rows = new Map<string, TeachingSession>()

  constructor(
    private readonly cards: FakeCardRepository,
    private readonly known: FakeKnownLemmaRepository,
  ) {}

  async load(trackId: TrackId): Promise<TeachingSession | undefined> {
    return this.rows.get(trackId)
  }

  async commit(
    session: TeachingSession,
    effects: readonly SessionEffect[],
  ): Promise<void> {
    for (const effect of effects) {
      if (effect.kind === 'saveCard') await this.cards.put(effect.card)
      else await this.known.add([effect.lemmaId])
    }

    if (session.phase === 'complete') this.rows.delete(session.trackId)
    else this.rows.set(session.trackId, session)
  }

  async clear(trackId: TrackId): Promise<void> {
    this.rows.delete(trackId)
  }
}

/**
 * Tracks in memory.
 *
 * Deliberately mirrors `DexieTrackRepository`'s *contract*, not its storage: it
 * keeps whole documents in a Map where the real one shreds them. The shredding
 * is an IndexedDB concern and nothing above the port can tell the difference,
 * which is the point of the port.
 */
export class FakeTrackRepository implements TrackRepository {
  readonly rows = new Map<
    TrackId,
    { document: TrackDocument; vocabulary: TrackVocabulary; importedAt: Date }
  >()

  async listTracks(): Promise<TrackSummary[]> {
    return [...this.rows.values()]
      .map(({ document, importedAt }) => ({
        id: document.track.id,
        title: document.track.title,
        artist: document.track.artist,
        homeDialect: document.track.homeDialect,
        dense: document.track.dense,
        wordTokens: document.track.wordTokens,
        uniqueWordTokens: document.track.uniqueWordTokens,
        importedAt,
      }))
      .sort((a, b) => b.importedAt.getTime() - a.importedAt.getTime())
  }

  async getTrack(id: TrackId): Promise<Track | undefined> {
    return this.rows.get(id)?.document.track
  }

  async getStanzas(id: TrackId): Promise<Stanza[]> {
    return this.rows.get(id)?.document.stanzas ?? []
  }

  async getTrackVocabulary(id: TrackId): Promise<TrackVocabulary | undefined> {
    return this.rows.get(id)?.vocabulary
  }

  async lexiconFor(id: TrackId): Promise<Map<LemmaKey, LexiconEntry>> {
    const document = this.rows.get(id)?.document
    return new Map(Object.entries(document?.lexicon ?? {}))
  }

  async saveTrack(document: TrackDocument, importedAt: Date): Promise<void> {
    this.rows.set(document.track.id, {
      document,
      vocabulary: countTrack(document.track.id, document.stanzas),
      importedAt,
    })
  }

  async deleteTrack(id: TrackId): Promise<void> {
    // The invariant, restated where a test could break it: no card store is
    // reachable from here, so this fake cannot unlearn anything either.
    this.rows.delete(id)
  }
}
