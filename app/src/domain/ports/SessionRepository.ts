/**
 * Storage port for a teaching session in progress.
 *
 * One open session per song, which is why the key is the track id and not a
 * session id. SPEC §11.1: one song is one session, and a song is never split —
 * so there is no second axis, where Molcajete needed `[bookId, chapterIndex]`.
 * There is no history to keep either: a finished session's result lives in the
 * cards it created.
 *
 * ## Why `commit` takes the effects as well as the session
 *
 * The obvious shape would be `put(session)` next to `CardRepository.put(card)`,
 * with the screen calling both. That has a failure mode this app is guaranteed
 * to hit: the card write lands, iOS suspends the tab before the session write,
 * and the resumed session shows a card it already graded. Grade it again and
 * FSRS gets two reviews for one answer — a schedule that is wrong rather than
 * merely stale.
 *
 * So one call, one transaction, both writes or neither. The effects come
 * straight from the session reducer, which is also why they are described as
 * data rather than performed by it.
 */

import type { TrackId } from '../types'
import type { SessionEffect, TeachingSession } from '../session/session'

export interface SessionRepository {
  load(trackId: TrackId): Promise<TeachingSession | undefined>

  /** Atomically: the session, plus every card and known lemma it produced. */
  commit(session: TeachingSession, effects: readonly SessionEffect[]): Promise<void>

  clear(trackId: TrackId): Promise<void>
}
