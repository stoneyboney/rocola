import { countTrack, type TrackVocabulary, type Vocabulary } from '../domain/coverage'
import type {
  TrackRepository,
  TrackSummary,
} from '../domain/ports/TrackRepository'
import type { Stanza, Track, TrackDocument } from '../domain/track'
import type { LemmaKey, LexiconEntry, TrackId } from '../domain/types'
import {
  db,
  type RocolaDatabase,
  type StoredVocabulary,
  type TrackRow,
} from './db'

/**
 * Songs in IndexedDB, shredded per track.
 *
 * ## `deleteTrack` names the stores it clears, one by one
 *
 * It would be shorter to loop over every table whose key starts with the track
 * id. That loop is the bug: `cards` and `knownLemmas` are keyed by lemma and
 * carry no track id, so they would not match today — but the shape of the code
 * would say "remove everything belonging to this song", and the next store
 * added is the one that gets swept up.
 *
 * `CardRepository`'s header states the rule: deleting a song removes its text
 * and does not unlearn its vocabulary. Naming four stores makes that a
 * deliberate list rather than a lucky accident of key design. There is a test
 * that teaches a card, deletes its song, and finds the card.
 */
export class DexieTrackRepository implements TrackRepository {
  constructor(private readonly database: RocolaDatabase = db) {}

  async listTracks(): Promise<TrackSummary[]> {
    const rows = await this.database.tracks.toArray()
    return rows
      .map(summaryOf)
      .sort((a, b) => b.importedAt.getTime() - a.importedAt.getTime())
  }

  async getTrack(id: TrackId): Promise<Track | undefined> {
    const row = await this.database.tracks.get(id)
    if (!row) return undefined
    const { importedAt: _importedAt, ...track } = row
    return track
  }

  async getStanzas(id: TrackId): Promise<Stanza[]> {
    const rows = await this.database.stanzas.where('trackId').equals(id).toArray()
    return rows
      .sort((a, b) => a.index - b.index)
      .map((row) => ({
        index: row.index,
        lines: row.lines,
        ...(row.repeatOf === undefined ? {} : { repeatOf: row.repeatOf }),
      }))
  }

  async getTrackVocabulary(id: TrackId): Promise<TrackVocabulary | undefined> {
    const row = await this.database.trackVocab.get(id)
    if (!row) return undefined
    return {
      trackId: row.trackId,
      all: fromStored(row.all),
      unique: fromStored(row.unique),
    }
  }

  async lexiconFor(id: TrackId): Promise<Map<LemmaKey, LexiconEntry>> {
    const rows = await this.database.lexicon.where('trackId').equals(id).toArray()
    return new Map(rows.map((row) => [row.key, row.entry]))
  }

  async saveTrack(
    document: TrackDocument,
    importedAt: Date = new Date(),
  ): Promise<void> {
    const { track, stanzas, lexicon } = document
    const { tracks, stanzas: stanzaTable, lexicon: lexiconTable, trackVocab } =
      this.database

    // Counted here, once, and both ways. `countTrack` is the only thing that
    // builds a `TrackVocabulary`, so a caller cannot end up with one count.
    const vocabulary = countTrack(track.id, stanzas)

    await this.database.transaction(
      'rw',
      [tracks, stanzaTable, lexiconTable, trackVocab],
      async () => {
        // Replace, not merge. A rebuilt song keeps its slug, and a stanza that
        // moved would otherwise survive at its old index.
        await stanzaTable.where('trackId').equals(track.id).delete()
        await lexiconTable.where('trackId').equals(track.id).delete()

        await tracks.put({ ...track, importedAt })
        await stanzaTable.bulkPut(
          stanzas.map((stanza) => ({
            trackId: track.id,
            index: stanza.index,
            lines: stanza.lines,
            ...(stanza.repeatOf === undefined ? {} : { repeatOf: stanza.repeatOf }),
          })),
        )
        await lexiconTable.bulkPut(
          Object.entries(lexicon).map(([key, entry]) => ({
            trackId: track.id,
            key,
            entry,
          })),
        )
        await trackVocab.put({
          trackId: track.id,
          all: toStored(vocabulary.all),
          unique: toStored(vocabulary.unique),
        })
      },
    )
  }

  async deleteTrack(id: TrackId): Promise<void> {
    const { tracks, stanzas, lexicon, trackVocab, positions } = this.database

    // Four stores, named. Not `cards`, not `knownLemmas`, not `sessions` —
    // see the header. A word met here stays learned.
    await this.database.transaction(
      'rw',
      [tracks, stanzas, lexicon, trackVocab, positions],
      async () => {
        await tracks.delete(id)
        await stanzas.where('trackId').equals(id).delete()
        await lexicon.where('trackId').equals(id).delete()
        await trackVocab.delete(id)
        await positions.delete(id)
      },
    )
  }
}

function summaryOf(row: TrackRow): TrackSummary {
  return {
    id: row.id,
    title: row.title,
    artist: row.artist,
    homeDialect: row.homeDialect,
    dense: row.dense,
    wordTokens: row.wordTokens,
    uniqueWordTokens: row.uniqueWordTokens,
    importedAt: row.importedAt,
  }
}

/** `Map` above, plain object below. See `db.ts`. */
function toStored(vocabulary: Vocabulary): StoredVocabulary {
  return {
    counts: Object.fromEntries(vocabulary.counts),
    propnTokens: vocabulary.propnTokens,
    tokenCount: vocabulary.tokenCount,
  }
}

function fromStored(stored: StoredVocabulary): Vocabulary {
  return {
    counts: new Map(Object.entries(stored.counts)),
    propnTokens: stored.propnTokens,
    tokenCount: stored.tokenCount,
  }
}
