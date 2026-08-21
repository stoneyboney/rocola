/**
 * What the reader renders. SPEC §10.
 *
 * The merge is the thing worth testing: consecutive untappable tokens become
 * one text run, which is what keeps punctuation from ever being an event
 * target for the delegated tap handler.
 */

import { describe, expect, it } from 'vitest'

import { buildLineView, buildReaderView } from '../../src/domain/view/readerView'
import type { Line, Stanza } from '../../src/domain/track'
import type { LemmaKey, LexiconEntry } from '../../src/domain/types'
import { entry, line, propn, punct, space, word } from '../fixture'

const LEXICON = new Map<LemmaKey, LexiconEntry>([
  ['k1', entry('cerro', { de: 'der Hügel' })],
  ['k2', entry('sierra', { de: 'das Gebirge' })],
  // Built by hand, not through `entry()`, which defaults a German gloss in.
  // A word with no `de` is a normal state and this file needs one.
  [
    'k3',
    {
      lemma: 'caballo',
      pos: 'NOUN',
      zipf: 4.1,
      uniqueLineCount: 1,
      variety: 'general',
      register: 'neutral',
    },
  ],
])

function view(l: Line, glossOnly: LemmaKey[] = []) {
  return buildLineView(l, new Set(glossOnly), LEXICON)
}

describe('runs, not tokens', () => {
  it('merges consecutive untappable tokens into one text run', () => {
    const built = view(
      line(0, 'El cerro, la sierra.', [
        word('El', 'el', 'f1', 'DET'),
        word('cerro', 'cerro', 'k1'),
        punct(','),
        word('sierra', 'sierra', 'k2'),
        punct('.'),
      ]),
    )

    // Every run that is not a word is text, and no two text runs are adjacent.
    built.runs.forEach((run, i) => {
      if (run.kind === 'text' && i > 0) {
        expect(built.runs[i - 1]!.kind).toBe('word')
      }
    })
  })

  it('makes punctuation part of a text run and never a word', () => {
    // The reason: the tap handler is delegated and matches `[data-t]`, so a
    // comma that became an element would be a comma you could tap.
    const built = view(
      line(0, 'cerro, sierra', [
        word('cerro', 'cerro', 'k1'),
        punct(','),
        word('sierra', 'sierra', 'k2'),
      ]),
    )
    const words = built.runs.filter((run) => run.kind === 'word')
    expect(words.map((run) => run.kind === 'word' && run.text)).toEqual([
      'cerro',
      'sierra',
    ])
  })

  it('leaves a proper noun untappable', () => {
    // A name carries a lemma and no lexicon key, so it merges into the text
    // and needs no rule of its own.
    const built = view(
      line(0, 'Durango', [propn('Durango')]),
    )
    expect(built.runs).toEqual([{ kind: 'text', text: 'Durango' }])
  })

  it('reconstructs the line exactly', () => {
    // Nothing is lost in the merge — this is what the reader shows, and §10.1
    // says a line is preserved as fetched.
    const original = line(0, '', [
      word('El', 'el', 'f1', 'DET'),
      word('cerro', 'cerro', 'k1'),
      punct(','),
      propn('Durango'),
      punct('.'),
    ])
    const built = view(original)
    const rebuilt = built.runs.map((run) => run.text).join('')
    expect(rebuilt).toBe(original.tokens.map((t) => t.s).join(''))
  })

  it('handles a line that is only punctuation', () => {
    const built = view(line(0, '...', [punct('.'), punct('.'), punct('.')]))
    expect(built.runs).toEqual([{ kind: 'text', text: '...' }])
  })

  it('handles an empty line', () => {
    expect(view(line(0, '', [])).runs).toEqual([])
  })
})

describe('the dotted underline and the reveal', () => {
  it('marks only glossOnly words', () => {
    const built = view(
      line(0, '', [word('cerro', 'cerro', 'k1'), space, word('sierra', 'sierra', 'k2')]),
      ['k2'],
    )
    const words = built.runs.filter((r) => r.kind === 'word')
    expect(words.map((r) => r.kind === 'word' && r.marked)).toEqual([false, true])
  })

  /** The first run, asserted to be a word so the test reads what it means. */
  function firstWord(built: { runs: readonly { kind: string }[] }) {
    const first = built.runs[0]
    expect(first?.kind).toBe('word')
    return first as { kind: 'word'; reveal: string | null; marked: boolean }
  }

  it('carries the German gloss for a marked word that has one', () => {
    const built = view(line(0, '', [word('sierra', 'sierra', 'k2')]), ['k2'])
    expect(firstWord(built).reveal).toBe('das Gebirge')
  })

  it('carries null for a marked word with no gloss', () => {
    // A normal state: Wiktionary misses, and the model rejects what it doubts.
    const built = view(line(0, '', [word('caballo', 'caballo', 'k3')]), ['k3'])
    expect(firstWord(built).reveal).toBeNull()
  })

  it('carries no reveal for a word that will be taught', () => {
    // §10.2 scopes the toggle to words that never got a card.
    const built = view(line(0, '', [word('cerro', 'cerro', 'k1')]), [])
    expect(firstWord(built).reveal).toBeNull()
  })
})

describe('repeats', () => {
  const chorus: Stanza = {
    index: 1,
    repeatOf: 0,
    lines: [{ ...line(2, 'Ay', [word('cerro', 'cerro', 'k1')]), repeatOf: 0 }],
  }

  it('marks a repeated stanza without removing it', () => {
    // §10.1: de-emphasised, never hidden. You are reading along.
    const built = buildReaderView(
      [{ index: 0, lines: [line(0, '', [word('cerro', 'cerro', 'k1')])] }, chorus],
      [],
      LEXICON,
    )
    expect(built.stanzas).toHaveLength(2)
    expect(built.stanzas[0]!.isRepeat).toBe(false)
    expect(built.stanzas[1]!.isRepeat).toBe(true)
    expect(built.stanzas[1]!.lines).toHaveLength(1)
  })

  it('marks a repeated line inside a stanza that is not itself a repeat', () => {
    const built = buildReaderView(
      [
        {
          index: 0,
          lines: [
            line(0, '', [word('cerro', 'cerro', 'k1')]),
            { ...line(1, '', [word('cerro', 'cerro', 'k1')]), repeatOf: 0 },
          ],
        },
      ],
      [],
      LEXICON,
    )
    expect(built.stanzas[0]!.isRepeat).toBe(false)
    expect(built.stanzas[0]!.lines.map((l) => l.isRepeat)).toEqual([false, true])
  })

  it('keeps line indices, which is what position restoration seeks on', () => {
    const built = buildReaderView([{ index: 0, lines: [line(7, '', [])] }], [], LEXICON)
    expect(built.stanzas[0]!.lines[0]!.index).toBe(7)
  })
})
