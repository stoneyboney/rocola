import { useCallback, useState } from 'react'
import { importFile, type ImportOutcome } from '../app/importFile'
import { useRepositories } from '../app/repositories'
import { navigate } from '../app/useRoute'
import { useAsync } from '../app/useAsync'
import { describeImportFailure, describeImportSuccess, dueCards } from './format'
import { ImportButton } from './ImportButton'
import { Screen } from './Screen'

/**
 * The home screen, standing where Molcajete's library stood.
 *
 * It is deliberately almost empty. The song list belongs to Phase 3, when
 * `Track` exists to list; what survives the fork is the pair of things that
 * never depended on there being a book: the seed import, and the chip that
 * appears when cards are due.
 *
 * Keeping the screen rather than deleting it with the library keeps `Review`
 * reachable — it is the only working flow in this build — and keeps the seam
 * where the import lands, so Phase 3 adds a list beneath it instead of
 * rebuilding the plumbing.
 */
export function Home() {
  const { known, cards, clock } = useRepositories()
  const [reloads, setReloads] = useState(0)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<{
    headline: string
    detail: string
  } | null>(null)
  const [done, setDone] = useState<string | null>(null)

  // SPEC §6.5. No chip when nothing is due — the app does not nag, and a zero
  // is not a thing worth drawing.
  const due = useAsync(() => cards.countDue(clock.now()), [cards, clock, reloads])

  const onFile = useCallback(
    async (file: File) => {
      setBusy(true)
      setFailure(null)
      setDone(null)
      try {
        const outcome: ImportOutcome = await importFile(file, { known })
        setDone(describeImportSuccess(outcome))
        setReloads((n) => n + 1)
      } catch (error) {
        setFailure(describeImportFailure(error))
      } finally {
        setBusy(false)
      }
    },
    [known],
  )

  return (
    <Screen
      title="Rocola"
      action={
        <ImportButton onFile={onFile} busy={busy} label="Wortschatz laden" />
      }
    >
      {due.status === 'ready' && dueCards(due.value) && (
        <button
          type="button"
          onClick={() => navigate({ name: 'review' })}
          className="border-rule mb-6 flex w-full items-center justify-between rounded-lg border px-4 py-3 text-left"
        >
          <span className="text-sm">{dueCards(due.value)}</span>
          <span className="text-accent text-sm">Wiederholen ›</span>
        </button>
      )}

      {done && (
        <p className="border-rule text-ink-muted mb-6 rounded-lg border border-dashed px-4 py-3 text-sm">
          {done}
        </p>
      )}

      {failure && (
        <div className="border-accent/40 bg-accent/5 mb-6 rounded-lg border px-4 py-3">
          <p className="text-sm">{failure.headline}</p>
          <p className="text-ink-muted mt-1 font-mono text-xs break-words">
            {failure.detail}
          </p>
        </div>
      )}

      <div className="text-ink-muted mt-16 text-center text-sm leading-relaxed text-balance">
        <p className="text-ink font-serif text-lg">Noch keine Lieder da.</p>
        <p className="mt-2">
          Die Songauswahl kommt aus deinen last.fm-Scrobbles und wird auf dem
          Rechner vorbereitet. Diese Version kann das noch nicht.
        </p>
        <p className="mt-4">
          Was jetzt schon geht: eine <span className="font-mono">known.json</span>{' '}
          aus <span className="font-mono">seed_known.py</span> laden — dein
          Anki-Wortschatz, damit dir nichts beigebracht wird, was du längst
          kannst — und fällige Karten wiederholen.
        </p>
      </div>
    </Screen>
  )
}
