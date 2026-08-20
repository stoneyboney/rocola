import type { SessionRepository } from '../domain/ports/SessionRepository'
import type { SessionEffect, TeachingSession } from '../domain/session/session'
import type { TrackId } from '../domain/types'
import { db, type RocolaDatabase } from './db'

/**
 * The session store, and the one transaction that makes an interrupted session
 * safe to resume.
 *
 * `commit` writes the session, every card it graded and every lemma it marked
 * known in a single `rw` transaction. Split across three calls, iOS suspending
 * the tab between them leaves a card that was graded inside a session that does
 * not know it — and re-grading on resume gives FSRS two reviews for one answer.
 */
export class DexieSessionRepository implements SessionRepository {
  constructor(private readonly database: RocolaDatabase = db) {}

  async load(trackId: TrackId): Promise<TeachingSession | undefined> {
    const row = await this.database.sessions.get(trackId)
    return row?.session
  }

  async commit(
    session: TeachingSession,
    effects: readonly SessionEffect[],
    markedAt: Date = session.updatedAt,
  ): Promise<void> {
    const { sessions, cards, knownLemmas } = this.database

    await this.database.transaction('rw', [sessions, cards, knownLemmas], async () => {
      for (const effect of effects) {
        if (effect.kind === 'saveCard') {
          await cards.put({ lemmaId: effect.card.lemmaId, card: effect.card })
        } else {
          await knownLemmas.put({ lemmaId: effect.lemmaId, markedAt })
        }
      }

      if (session.phase === 'complete') {
        // Nothing to resume, and the result is in the cards. Keeping finished
        // sessions would only give `load` something to filter.
        await sessions.delete(session.trackId)
      } else {
        await sessions.put({ trackId: session.trackId, session })
      }
    })
  }

  async clear(trackId: TrackId): Promise<void> {
    await this.database.sessions.delete(trackId)
  }
}
