/**
 * Storage port for songs.
 *
 * CLAUDE.md rule 4: this interface is the only thing the app knows about
 * persistence. In Swift the same interface gets a SwiftData implementation and
 * nothing above it changes.
 *
 * ## A track is stored shredded, not as one document
 *
 * One row for the track, one per stanza, one per lexicon entry, the track id in
 * every compound key. Molcajete shredded a book because `las-noches-mejicanas`
 * is 11 MB and opening one chapter should not deserialise all of it. A song is
 * 20 KB and gains nothing from that.
 *
 * What survives at song scale is the *shape*: the repository hands out what a
 * screen needs. The song list reads `listTracks` and `getTrackVocabulary` and
 * never touches a token. The reader reads stanzas and a lexicon for one id.
 *
 * **There is deliberately no `getTrackDocument`.** Molcajete left the same note
 * about `getBundle`: reintroducing one would undo the arrangement in a single
 * line, because the easiest thing to do with it is read everything everywhere.
 *
 * ## `deleteTrack` and the invariant it is most likely to break
 *
 * See `CardRepository`, which says it plainly: there is no track id anywhere in
 * that interface, and deleting a song removes its text without unlearning its
 * vocabulary. A word met in one song must not be taught again in another just
 * because the first song was removed.
 *
 * The tidy implementation of `deleteTrack` — one transaction clearing every
 * store keyed by this id — is exactly that bug. There is a test.
 */

import type { TrackVocabulary } from '../coverage'
import type { Stanza, Track, TrackDocument } from '../track'
import type { LemmaKey, LexiconEntry, TrackId, Variety } from '../types'

/** Everything the song list draws, and nothing that needs a token read. */
export interface TrackSummary {
  id: TrackId
  title: string
  artist: string
  /** The dialect every regional judgement in this track was made against. */
  homeDialect: Variety
  /** §11.1: over the 18-card cap. Surfaced for the reader, never acted on. */
  dense: boolean
  wordTokens: number
  uniqueWordTokens: number
  importedAt: Date
}

export interface TrackRepository {
  listTracks(): Promise<TrackSummary[]>

  getTrack(id: TrackId): Promise<Track | undefined>

  /** The whole song, in order, repeats included. What the reader renders. */
  getStanzas(id: TrackId): Promise<Stanza[]>

  /**
   * Both counts, computed once at import.
   *
   * Never one of them: `all` is coverage's denominator and `unique` is the
   * teach set's, and a caller that receives only one has had a question
   * answered it did not ask.
   */
  getTrackVocabulary(id: TrackId): Promise<TrackVocabulary | undefined>

  /** Every entry for this track, for one bulk read before the reader opens. */
  lexiconFor(id: TrackId): Promise<Map<LemmaKey, LexiconEntry>>

  /**
   * Store a parsed track, replacing any earlier import of the same id.
   *
   * Replacing rather than adding, because the id is a slug: rebuilding a song
   * after a re-gloss produces the same id and must not leave two rows.
   */
  saveTrack(document: TrackDocument, importedAt: Date): Promise<void>

  /** Removes the song. **Leaves cards and known lemmas alone.** */
  deleteTrack(id: TrackId): Promise<void>
}
