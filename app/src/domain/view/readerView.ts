/**
 * Turns a song's token arrays into what the reader renders.
 *
 * Ported from Molcajete's chapter reader, minus the parts that only earned
 * their place at book scale. What carried over is the merge:
 *
 * Consecutive tokens that are not tappable — whitespace, punctuation, numerals,
 * and proper nouns, which carry no lexicon key — become a single text run.
 * `Camino solo por` is two runs, not five, and only the words are elements.
 *
 * Molcajete measured this on a 68,979-token chapter, where it more than halved
 * the element count. A song has a few hundred tokens and would render fine
 * either way, so the honest reason to keep it is not performance: a text node
 * has no box, no class and is never an event target, and *not* making
 * punctuation an event target is what keeps the delegated tap handler simple.
 *
 * ## What was deliberately not ported
 *
 * `estimatedHeightPx` and the `content-visibility` machinery it fed. Those
 * exist so that a 1,046-paragraph chapter can skip layout for what is off
 * screen while keeping the scrollbar honest. A song is 44 lines. Carrying them
 * would mean maintaining a height model for a document you can nearly see at
 * once.
 */

import { isTappable, type LemmaKey, type LexiconEntry } from '../types'
import type { Line, Stanza } from '../track'

export interface TextRun {
  kind: 'text'
  text: string
}

export interface WordRun {
  kind: 'word'
  text: string
  key: LemmaKey
  /** In this song's `glossOnly` list: gets the dotted underline. */
  marked: boolean
  /**
   * The German gloss shown above the word while "reveal all" is on. Non-null
   * only for marked words that actually have one — the toggle is scoped to the
   * words that never got a card.
   */
  reveal: string | null
}

export type Run = TextRun | WordRun

export interface LineView {
  index: number
  runs: Run[]
  /** True when an earlier line said the same thing. */
  isRepeat: boolean
}

export interface StanzaView {
  index: number
  lines: LineView[]
  /**
   * True when this whole stanza repeats an earlier one. §10.1 de-emphasises it
   * — a left rule or reduced opacity — and never hides it: you are reading
   * along, and the chorus is part of the song.
   */
  isRepeat: boolean
}

export interface ReaderView {
  stanzas: StanzaView[]
}

export function buildLineView(
  line: Line,
  glossOnly: ReadonlySet<LemmaKey>,
  lexicon: ReadonlyMap<LemmaKey, LexiconEntry>,
): LineView {
  const runs: Run[] = []
  let pending = ''

  const flush = () => {
    if (pending !== '') {
      runs.push({ kind: 'text', text: pending })
      pending = ''
    }
  }

  for (const token of line.tokens) {
    if (!isTappable(token)) {
      pending += token.s
      continue
    }
    flush()
    const marked = glossOnly.has(token.t)
    runs.push({
      kind: 'word',
      text: token.s,
      key: token.t,
      marked,
      reveal: marked ? (lexicon.get(token.t)?.de ?? null) : null,
    })
  }
  flush()

  return { index: line.index, runs, isRepeat: line.repeatOf !== undefined }
}

export function buildReaderView(
  stanzas: readonly Stanza[],
  glossOnly: readonly LemmaKey[],
  lexicon: ReadonlyMap<LemmaKey, LexiconEntry>,
): ReaderView {
  const marked = new Set(glossOnly)
  return {
    stanzas: stanzas.map((stanza) => ({
      index: stanza.index,
      isRepeat: stanza.repeatOf !== undefined,
      lines: stanza.lines.map((line) => buildLineView(line, marked, lexicon)),
    })),
  }
}
