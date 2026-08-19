import { useCallback, useState } from 'react'
import { useRepositories } from '../app/repositories'
import type { ReviewGrade } from '../domain/srs/scheduler'
import type { LemmaKey, LexiconEntry } from '../domain/types'
import {
  grade as applyGrade,
  introduce as applyIntroduce,
  type IntroductionAction,
  type TeachingSession as Session,
} from '../domain/session/session'
import { buildSessionView } from '../domain/view/sessionView'
import { GRADE_LABELS, sessionProgress } from './format'
import { CardAnswer, CardFront } from './SessionCard'
import { Screen } from './Screen'

const GRADES: ReviewGrade[] = ['again', 'hard', 'good', 'easy']

/**
 * SPEC §6.3, one card at a time, full screen.
 *
 * Two things this screen is careful about.
 *
 * **Every answer is persisted before the next card appears.** `commit` is
 * awaited and the buttons are disabled while it runs, so there is no window in
 * which a card has been answered on screen but not in storage. This is a phone;
 * the tab gets suspended mid-session and has to come back on the same card.
 *
 * **It computes nothing** (rule 5). Phase, current card, progress and the
 * German copy all arrive ready-made.
 *
 * ## Why it takes a session rather than fetching one
 *
 * Molcajete's version took a `bookId` and a `chapterIndex` and called
 * `loadSession` to turn them into a session and a lexicon slice. That loader was
 * entirely about finding a chapter, and it is gone with the chapter (SPEC §3).
 *
 * Rather than delete the screen with it, the loading moved out: it now receives
 * a session and the lexicon that glosses it, and owns only the part that was
 * never book-shaped — reveal, grade, commit, resume. Phase 3 supplies both from
 * a `Track` and calls this unchanged.
 *
 * Nothing routes here yet. That is expected: this build has no songs.
 */
export function TeachingSession({
  session: initial,
  lexicon,
  onBack,
  onDone,
}: {
  session: Session
  lexicon: ReadonlyMap<LemmaKey, LexiconEntry>
  /** Where the back control goes. The caller owns navigation. */
  onBack: { label: string; onClick: () => void }
  /** Offered when the session completes. Omit and no button is drawn. */
  onDone?: { label: string; onClick: () => void }
}) {
  const { cards, sessions, clock } = useRepositories()

  const [session, setSession] = useState<Session>(initial)
  const [revealed, setRevealed] = useState(false)
  const [busy, setBusy] = useState(false)

  const commit = useCallback(
    async (next: Session, effects: Parameters<typeof sessions.commit>[1]) => {
      setBusy(true)
      try {
        await sessions.commit(next, effects)
        setSession(next)
        setRevealed(false)
      } finally {
        setBusy(false)
      }
    },
    [sessions],
  )

  const onIntroduce = useCallback(
    (action: IntroductionAction) => {
      if (!session || busy) return
      const step = applyIntroduce(session, action, clock.now())
      void commit(step.session, step.effects)
    },
    [session, busy, clock, commit],
  )

  const onGrade = useCallback(
    async (reviewGrade: ReviewGrade) => {
      if (!session || busy) return
      const card = session.queue[0]
      if (!card) return
      // The word may already have a schedule from an earlier song.
      const existing = await cards.get(card.lemmaId)
      const step = applyGrade(session, reviewGrade, clock.now(), existing)
      void commit(step.session, step.effects)
    },
    [session, busy, cards, clock, commit],
  )

  const view = buildSessionView(session, lexicon)

  if (view.phase === 'complete') {
    return (
      <Screen title="Fertig" back={onBack}>
        <p className="text-lg">
          {view.total === 0
            ? 'Hier gibt es nichts mehr zu lernen.'
            : `${sessionProgress(view.passed + view.dismissed, view.total)} Karten erledigt.`}
        </p>
        {view.dismissed > 0 && (
          <p className="text-ink-muted mt-2 text-sm">
            {view.dismissed} davon kanntest du schon.
          </p>
        )}
        {onDone && (
          <button
            type="button"
            onClick={onDone.onClick}
            className="bg-accent mt-8 w-full rounded-xl px-4 py-3.5 text-base text-white"
          >
            {onDone.label}
          </button>
        )}
      </Screen>
    )
  }

  const card = view.card!

  return (
    <Screen title="Lernen" back={onBack}>
      <div className="flex items-center gap-3">
        <span className="bg-rule h-1 flex-1 overflow-hidden rounded-full">
          <span
            className="bg-accent block h-full transition-[width] duration-200"
            style={{ width: `${view.fraction * 100}%` }}
          />
        </span>
        <span className="text-ink-faint shrink-0 text-xs tabular-nums">
          {sessionProgress(view.answered, view.total)}
        </span>
      </div>

      {view.phase === 'introduction' ? (
        <div className="mt-10">
          <CardFront view={card} />
          <CardAnswer view={card} />

          <div className="mt-10 flex gap-3">
            <button
              type="button"
              disabled={busy}
              onClick={() => onIntroduce('ichKenneDas')}
              className="border-rule flex-1 rounded-xl border px-4 py-3.5 text-base disabled:opacity-50"
            >
              Ich kenne das
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => onIntroduce('weiter')}
              className="bg-accent flex-1 rounded-xl px-4 py-3.5 text-base text-white disabled:opacity-50"
            >
              Weiter
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-10">
          <CardFront view={card} />

          {revealed ? (
            <>
              <CardAnswer view={card} />
              <div className="mt-10 grid grid-cols-4 gap-2">
                {GRADES.map((reviewGrade) => (
                  <button
                    key={reviewGrade}
                    type="button"
                    disabled={busy}
                    onClick={() => void onGrade(reviewGrade)}
                    className="border-rule rounded-xl border px-2 py-3.5 text-sm disabled:opacity-50"
                  >
                    {GRADE_LABELS[reviewGrade]}
                  </button>
                ))}
              </div>
            </>
          ) : (
            <button
              type="button"
              onClick={() => setRevealed(true)}
              className="border-rule text-ink-muted mt-10 w-full rounded-xl border border-dashed px-4 py-6 text-sm"
            >
              Antippen zum Aufdecken
            </button>
          )}
        </div>
      )}
    </Screen>
  )
}
