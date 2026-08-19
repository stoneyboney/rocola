/**
 * The teaching flow, end to end: select, teach, commit, look again.
 *
 * This is the only test above `tests/domain/` and it is here because the claims
 * it checks are claims about the *flow* rather than about any one function.
 *
 * ## What changed at the fork
 *
 * Molcajete ran this against `loadSession`, which turned a book id and a
 * chapter index into a session by way of `BookRepository`. That loader was
 * entirely about finding a chapter and is gone with the chapter (SPEC §3), so
 * the equivalent lives here as `openSession` — the same two rules, over the
 * synthetic fixture instead of a stored book:
 *
 *   1. A stored session is resumed exactly, never recomputed. Re-selecting
 *      would change the contents of a session already in progress.
 *   2. Otherwise the teach set is recomputed from the text's own lemma counts
 *      against the live known-set.
 *
 * Phase 3 puts this back behind a real loader once a `Track` exists to load.
 * When it does, these assertions should survive unchanged.
 */

import { describe, expect, it } from 'vitest'
import { computeCoverage, countVocabulary } from '../src/domain/coverage'
import { buildKnownState, type KnownState } from '../src/domain/knownLemmas'
import { lemmaId } from '../src/domain/lemma'
import type { CardRepository } from '../src/domain/ports/CardRepository'
import type { KnownLemmaRepository } from '../src/domain/ports/KnownLemmaRepository'
import type { SessionRepository } from '../src/domain/ports/SessionRepository'
import {
  grade,
  introduce,
  isComplete,
  startSession,
  type TeachingSession,
} from '../src/domain/session/session'
import { gradeCard } from '../src/domain/srs/scheduler'
import {
  CLOSED_CLASS_POS,
  DEFAULT_TEACH_SET_OPTIONS,
  selectTeachSet,
} from '../src/domain/teachSet'
import {
  FakeCardRepository,
  FakeKnownLemmaRepository,
  FakeSessionRepository,
} from './fakes'
import { fixedClock } from './clock'
import { LEXICON, lexiconMap, paragraphs } from './fixture'

const TRACK = 'cancion-sintetica'
const START = new Date('2026-01-01T09:00:00Z')

/** The eight open-class words of the fixture. See tests/fixture.ts. */
const TEACHABLE = 8
/** 17 word tokens, of which 1 is the proper noun that is covered for free. */
const TOKENS = 17

interface App {
  cards: FakeCardRepository
  known: FakeKnownLemmaRepository
  sessions: FakeSessionRepository
}

function freshApp(): App {
  const cards = new FakeCardRepository()
  const known = new FakeKnownLemmaRepository()
  return { cards, known, sessions: new FakeSessionRepository(cards, known) }
}

async function loadKnownState(
  cards: CardRepository,
  known: KnownLemmaRepository,
): Promise<KnownState> {
  const [carded, marked] = await Promise.all([
    cards.listCardedLemmas(),
    known.listAll(),
  ])
  const full = await cards.getMany([...carded])
  return buildKnownState(full.values(), marked)
}

/** What `loadSession` did, minus the part that went looking for a chapter. */
async function openSession(
  app: App & { sessions: SessionRepository },
  now: Date = START,
): Promise<{ session: TeachingSession; resumed: boolean; state: KnownState }> {
  const state = await loadKnownState(app.cards, app.known)

  const stored = await app.sessions.load(TRACK, 0)
  if (stored) return { session: stored, resumed: true, state }

  const lexicon = lexiconMap()
  const vocabulary = countVocabulary(paragraphs())
  const { teach } = selectTeachSet(
    vocabulary.counts,
    lexicon,
    // A word with a card must not be taught again, whether or not it has
    // matured. Known and carded are different tests and collapsing them
    // breaks one or the other.
    new Set([...state.known, ...state.carded]),
    DEFAULT_TEACH_SET_OPTIONS,
  )

  const session = startSession(
    TRACK,
    0,
    teach.map((key) => {
      const entry = lexicon.get(key)!
      return {
        key,
        lemmaId: lemmaId(entry),
        // Copied onto the card at creation, so the cross-song review screen
        // can render it without the song. See `CardFace`.
        face: {
          pos: entry.pos,
          de: entry.de ?? null,
          en: entry.en ?? null,
          example: entry.example?.es ?? null,
          regionNote: entry.regionNote ?? null,
          mexicanism: entry.mexicanism,
        },
      }
    }),
    now,
  )
  return { session, resumed: false, state }
}

/** Run a whole session the way the screen does: answer, commit, repeat. */
async function runSession(
  app: App,
  answer: (session: TeachingSession) => 'weiter' | 'ichKenneDas' | 'good' | 'again',
  clock = fixedClock(START),
): Promise<TeachingSession> {
  let { session } = await openSession(app, clock.now())
  let guard = 0
  while (!isComplete(session) && guard++ < 500) {
    const action = answer(session)
    const step =
      action === 'weiter' || action === 'ichKenneDas'
        ? introduce(session, action, clock.now())
        : grade(
            session,
            action,
            clock.now(),
            await app.cards.get(session.queue[0]!.lemmaId),
          )
    await app.sessions.commit(step.session, step.effects)
    session = step.session
  }
  return session
}

const alwaysGood = (session: TeachingSession) =>
  session.phase === 'introduction' ? ('weiter' as const) : ('good' as const)

describe('the first session', () => {
  it('teaches every open-class word and nothing else', async () => {
    const app = freshApp()
    const { session, resumed } = await openSession(app)

    expect(session.total).toBe(TEACHABLE)
    expect(resumed).toBe(false)
  })

  it('writes a card for every word it taught', async () => {
    const app = freshApp()
    const session = await runSession(app, alwaysGood)

    expect(isComplete(session)).toBe(true)
    expect(app.cards.rows.size).toBe(TEACHABLE)
    expect(app.known.rows.size).toBe(0)
  })

  it('leaves nothing to teach afterwards, without calling it known', async () => {
    // Cards exist, so the words are not taught again. They have not matured,
    // so they do not count towards coverage yet. Both at once — collapsing
    // "has a card" and "is known" breaks one or the other.
    const app = freshApp()
    await runSession(app, alwaysGood)

    const { session, state } = await openSession(app)
    expect(session.total).toBe(0)
    expect(state.carded.size).toBe(TEACHABLE)
    expect(state.known.size).toBe(0)
  })
})

describe('coverage', () => {
  it('stays flat right after a session, because a fresh card is not known', async () => {
    const app = freshApp()
    await runSession(app, alwaysGood)
    const { state } = await openSession(app)

    const coverage = computeCoverage(
      countVocabulary(paragraphs()),
      lexiconMap(),
      state.known,
    )
    // Only the proper noun is covered: 1 of 17.
    expect(coverage).toBeCloseTo(1 / TOKENS)
  })

  it('rises once those cards mature', async () => {
    const app = freshApp()
    const clock = fixedClock(START)

    // Study, then answer again each time the cards fall due, until they pass
    // SPEC §7's 21-day stability threshold. No real time passes.
    await runSession(app, alwaysGood, clock)
    for (let round = 0; round < 6; round++) {
      clock.advanceDays(30)
      for (const card of [...app.cards.rows.values()]) {
        await app.cards.put(gradeCard(card, 'good', clock.now()))
      }
    }

    const { state } = await openSession(app, clock.now())
    expect(state.known.size).toBe(TEACHABLE)

    const coverage = computeCoverage(
      countVocabulary(paragraphs()),
      lexiconMap(),
      state.known,
    )
    // 8 open-class tokens + 1 proper noun, of 17.
    expect(coverage).toBeCloseTo(9 / TOKENS)
  })

  it('caps below the warning threshold until function words are seeded', async () => {
    // Worth pinning, because it looks like a bug and is not. Learning every
    // word this text will ever teach reaches 9 of its 17 word tokens. The
    // other 8 are el×4, de×3, y — closed-class words the teach set
    // deliberately never contains.
    //
    // Coverage therefore understates readability by design until SPEC §8's
    // Anki seed marks the function words known. Until then the warning fires
    // on everything, and it is the warning that is premature, not the
    // arithmetic. Do not "fix" this by teaching `el`.
    const lexicon = lexiconMap()
    const vocabulary = countVocabulary(paragraphs())
    const { teach } = selectTeachSet(
      vocabulary.counts,
      lexicon,
      new Set(),
      DEFAULT_TEACH_SET_OPTIONS,
    )

    const everythingTeachable = new Set(teach.map((key) => lexicon.get(key)!.lemma))
    const ceiling = computeCoverage(vocabulary, lexicon, everythingTeachable)

    expect(ceiling).toBeCloseTo(9 / TOKENS)
    expect(ceiling).toBeLessThan(0.95)

    // And the remainder really is closed class, not something we forgot.
    const uncovered = [...vocabulary.counts.keys()]
      .map((key) => lexicon.get(key)!)
      .filter((entry) => !everythingTeachable.has(entry.lemma))
    expect(uncovered).not.toHaveLength(0)
    for (const entry of uncovered) {
      expect(CLOSED_CLASS_POS.has(entry.pos)).toBe(true)
    }
  })
})

describe('"Ich kenne das"', () => {
  it('removes the word from every future teach set', async () => {
    const app = freshApp()
    const { session } = await openSession(app)
    const first = session.queue[0]!

    const step = introduce(session, 'ichKenneDas', START)
    await app.sessions.commit(step.session, step.effects)

    expect(app.known.rows.has(first.lemmaId)).toBe(true)
    // And no card was created — it is not a review.
    expect(app.cards.rows.size).toBe(0)
  })

  it('counts towards coverage immediately, unlike a fresh card', async () => {
    const app = freshApp()
    let { session } = await openSession(app)
    for (let i = 0; i < 5; i++) {
      const step = introduce(session, 'ichKenneDas', START)
      await app.sessions.commit(step.session, step.effects)
      session = step.session
    }

    const { state } = await openSession(app)
    expect(state.known.size).toBe(5)

    const coverage = computeCoverage(
      countVocabulary(paragraphs()),
      lexiconMap(),
      state.known,
    )
    expect(coverage).toBeCloseTo(6 / TOKENS)
  })
})

describe('an interrupted session', () => {
  it('resumes on the same card rather than starting over', async () => {
    const app = freshApp()
    let { session } = await openSession(app)

    // Get into the recall phase, then answer a few.
    for (let i = 0; i < TEACHABLE; i++) {
      const step = introduce(session, 'weiter', START)
      await app.sessions.commit(step.session, step.effects)
      session = step.session
    }
    for (let i = 0; i < 3; i++) {
      const step = grade(session, 'good', START)
      await app.sessions.commit(step.session, step.effects)
      session = step.session
    }

    // The tab dies here. Everything below comes back from storage only.
    const resumed = await openSession(app)

    expect(resumed.resumed).toBe(true)
    expect(resumed.session.phase).toBe('recall')
    expect(resumed.session.passed).toHaveLength(3)
    expect(resumed.session.queue[0]?.key).toBe(session.queue[0]?.key)
    expect(resumed.session.total).toBe(TEACHABLE)
  })

  it('does not recompute a session in progress', async () => {
    // Re-selecting on resume would change the contents of a running session:
    // the cards already graded now have cards and would drop out.
    const app = freshApp()
    let { session } = await openSession(app)
    for (let i = 0; i < TEACHABLE; i++) {
      const step = introduce(session, 'weiter', START)
      await app.sessions.commit(step.session, step.effects)
      session = step.session
    }
    const step = grade(session, 'good', START)
    await app.sessions.commit(step.session, step.effects)

    const resumed = await openSession(app)
    expect(resumed.session.total).toBe(TEACHABLE)
    expect(resumed.session.queue).toHaveLength(TEACHABLE - 1)
  })

  it('starts a fresh, empty session once the last one completed', async () => {
    const app = freshApp()
    await runSession(app, alwaysGood)

    const next = await openSession(app)
    expect(next.resumed).toBe(false)
    expect(next.session.total).toBe(0)
    expect(isComplete(next.session)).toBe(true)
  })
})

describe('cards are global', () => {
  it('does not re-teach a word met in another song', async () => {
    // `CardRepository` has no owning id anywhere in it, which is what makes
    // this true rather than merely usual. The second song is the same text
    // under a different id; matching happens on the lemma, not the key.
    const app = freshApp()
    await runSession(app, alwaysGood)

    const state = await loadKnownState(app.cards, app.known)
    const lexicon = lexiconMap()
    const { teach } = selectTeachSet(
      countVocabulary(paragraphs()).counts,
      lexicon,
      new Set([...state.known, ...state.carded]),
      DEFAULT_TEACH_SET_OPTIONS,
    )

    expect(teach).toEqual([])
    expect(Object.keys(LEXICON).length).toBeGreaterThan(teach.length)
  })
})
