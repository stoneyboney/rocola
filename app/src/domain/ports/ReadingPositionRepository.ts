/**
 * Where you were in a song.
 *
 * A line index rather than a scroll offset, for the reason Molcajete kept a
 * paragraph id: the same position has to mean the same thing at a different
 * type size, in landscape, and on a phone instead of an iPad. Pixels do not
 * survive any of those.
 *
 * ## Worth less here than it was in a book, and built anyway
 *
 * Molcajete restored a position inside an 1,136-paragraph chapter, where losing
 * it meant hunting for your place. A song is one or two screens — you can
 * usually see where you were. The honest reason this exists is that it is in
 * the definition of done, plus the long songs where it still helps.
 *
 * Kept deliberately small because of that: two methods, no history, no
 * fractional offset within the line.
 */

import type { TrackId } from '../types'

export interface ReadingPosition {
  trackId: TrackId
  /** Index into the document's lines, repeats included — what the reader shows. */
  lineIndex: number
  updatedAt: Date
}

export interface ReadingPositionRepository {
  get(trackId: TrackId): Promise<ReadingPosition | undefined>
  save(trackId: TrackId, lineIndex: number, now: Date): Promise<void>
}
