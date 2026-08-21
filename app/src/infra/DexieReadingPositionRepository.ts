import type {
  ReadingPosition,
  ReadingPositionRepository,
} from '../domain/ports/ReadingPositionRepository'
import type { TrackId } from '../domain/types'
import { db, type RocolaDatabase } from './db'

/**
 * One row per song you have opened. Overwritten, never appended to — there is
 * no reading history worth keeping for a document you can see most of at once.
 */
export class DexieReadingPositionRepository implements ReadingPositionRepository {
  constructor(private readonly database: RocolaDatabase = db) {}

  async get(trackId: TrackId): Promise<ReadingPosition | undefined> {
    return this.database.positions.get(trackId)
  }

  async save(trackId: TrackId, lineIndex: number, now: Date): Promise<void> {
    await this.database.positions.put({ trackId, lineIndex, updatedAt: now })
  }
}
