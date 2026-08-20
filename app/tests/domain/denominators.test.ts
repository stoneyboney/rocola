/**
 * THE TWO DENOMINATORS.
 *
 * A song is counted twice, over two different sets of lines, and the answers
 * differ on purpose:
 *
 *     countVocabulary(uniqueLinesOf(stanzas))  ->  the teach set   §7.4
 *     countVocabulary(linesOf(stanzas))        ->  coverage        §11.2
 *
 * Both numbers land on the same screen, which is what makes them easy to
 * confuse. If one is computed and reused for the other, one of them is quietly
 * wrong and nothing in the app will say which. These tests are the thing that
 * says which.
 */

import { describe, expect, it } from 'vitest'

import { computeCoverage, countTrack, countVocabulary } from '../../src/domain/coverage'
import { lemmaId } from '../../src/domain/lemma'
import { linesOf, uniqueLinesOf } from '../../src/domain/track'
import { selectTeachSet } from '../../src/domain/teachSet'
import { LEXICON, lexiconMap, stanzas, withRepeatedStanza } from '../fixture'

describe('the two counts disagree, and that is the point', () => {
  it('a repeated stanza inflates one and not the other', () => {
    const counted = countTrack('t', withRepeatedStanza(4))

    expect(counted.all.tokenCount).toBeGreaterThan(counted.unique.tokenCount)
    // The unique count matches the song with the chorus sung once.
    expect(counted.unique.tokenCount).toBe(countTrack('t', stanzas()).all.tokenCount)
  })

  it('a song with no repeats counts the same both ways', () => {
    const counted = countTrack('t', stanzas())
    expect(counted.all.tokenCount).toBe(counted.unique.tokenCount)
    expect(counted.all.counts).toEqual(counted.unique.counts)
  })

  it('the counts really do diverge, and by a lot', () => {
    // The premise everything else rests on. With the chorus sung four times,
    // `cantar` occurs four times across all lines and once across unique ones.
    const lexicon = lexiconMap()
    const four = countTrack('t', withRepeatedStanza(4))
    const keyOf = (lemma: string) =>
      [...lexicon].find(([, entry]) => entry.lemma === lemma)![0]

    expect(four.all.counts.get(keyOf('cantar'))).toBe(4)
    expect(four.unique.counts.get(keyOf('cantar'))).toBe(1)
    // A verse word is unaffected, which is what makes the ratio wrong rather
    // than merely the scale.
    expect(four.all.counts.get(keyOf('cerro'))).toBe(1)
    expect(four.unique.counts.get(keyOf('cerro'))).toBe(1)
  })

  it('the teach set is insulated from the choice, and here is why', () => {
    // Worth pinning precisely because it is *narrower* than it looks.
    //
    // `selectTeachSet` ranks by the lexicon entry's `uniqueLineCount` — a
    // number the pipeline computed over unique lines — and uses the counts map
    // only to decide which keys are present. A repeated line contains no lemma
    // its first occurrence did not, so the membership is identical too.
    //
    // So passing the wrong counts here is currently harmless. If anyone ever
    // changes the ranking to read the passed counts, this test fails and the
    // two-denominator hazard becomes real for the teach set as well as for
    // coverage. That is the failure it exists to announce.
    const lexicon = lexiconMap()
    const four = countTrack('t', withRepeatedStanza(4))

    const fromUnique = selectTeachSet(four.unique.counts, lexicon, new Set())
    const fromAll = selectTeachSet(four.all.counts, lexicon, new Set())
    expect(fromAll.teach).toEqual(fromUnique.teach)

    const once = countTrack('t', stanzas())
    expect(fromUnique.teach).toEqual(
      selectTeachSet(once.unique.counts, lexicon, new Set()).teach,
    )
  })

  it('`all` is what coverage must be measured over', () => {
    // You read the chorus five times. A chorus you know is readable five
    // times, and one you do not is a wall you hit five times.
    const lexicon = lexiconMap()
    const counted = countTrack('t', withRepeatedStanza(4))
    const knowsChorus = new Set(
      // The second stanza's open-class words.
      ['cantar', 'luna', 'sombra', 'camino', 'viejo'].map((lemma) =>
        lemmaId({ ...LEXICON.k1!, lemma }),
      ),
    )

    const overAll = computeCoverage(counted.all, lexicon, knowsChorus)
    const overUnique = computeCoverage(counted.unique, lexicon, knowsChorus)

    // Knowing the repeated part is worth *more* when every repeat is counted,
    // which is the true statement about reading the page.
    expect(overAll).toBeGreaterThan(overUnique)
  })

  it('coverage still reaches 1 when everything is known, either way', () => {
    const lexicon = lexiconMap()
    const counted = countTrack('t', withRepeatedStanza(3))
    const everything = new Set(Object.values(LEXICON).map(lemmaId))

    expect(computeCoverage(counted.all, lexicon, everything)).toBe(1)
    expect(computeCoverage(counted.unique, lexicon, everything)).toBe(1)
  })
})

describe('the shape enforces the choice', () => {
  it('there is no such thing as the vocabulary of a track', () => {
    // `countTrack` returns both, named. A caller cannot ask for "the counts";
    // it asks for `all` or `unique`, and the name says which question it
    // answered. That is the whole enforcement.
    const counted = countTrack('t', stanzas())
    expect(Object.keys(counted).sort()).toEqual(['all', 'trackId', 'unique'])
  })

  it('linesOf and uniqueLinesOf are the two inputs', () => {
    const repeated = withRepeatedStanza(3)
    expect(linesOf(repeated).length).toBeGreaterThan(
      uniqueLinesOf(repeated).length,
    )
    expect(uniqueLinesOf(repeated)).toHaveLength(linesOf(stanzas()).length)
  })

  it('counting the two line sets by hand agrees with countTrack', () => {
    const repeated = withRepeatedStanza(2)
    const counted = countTrack('t', repeated)
    expect(counted.all).toEqual(countVocabulary(linesOf(repeated)))
    expect(counted.unique).toEqual(countVocabulary(uniqueLinesOf(repeated)))
  })
})
