import { useCallback, useState } from 'react'
import { importFile, type ImportOutcome } from '../app/importFile'
import { useRepositories } from '../app/repositories'
import { navigate } from '../app/useRoute'
import { useAsync } from '../app/useAsync'
import { buildKnownState } from '../domain/knownLemmas'
import {
  buildTrackListView,
  type TrackListInput,
  type TrackListView,
} from '../domain/view/trackListView'
import {
  cardsToLearn,
  describeImportFailure,
  describeImportSuccess,
  dueCards,
  percent,
} from './format'
import { ImportButton } from './ImportButton'
import { Screen } from './Screen'

/**
 * The home screen: the songs you have, and the chip when something is due.
 *
 * Computes nothing (rule 5). The two numbers on each row come from different
 * denominators — cards over unique lines, coverage over every line — and both
 * are decided in `trackListView`, which is also where the reason is written
 * down. A component that derived either of them would be the place the
 * distinction quietly died.
 */
export function Home() {
  const { known, cards, tracks, clock } = useRepositories()
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

  const list = useAsync<TrackListView>(async () => {
    const summaries = await tracks.listTracks()
    const inputs: TrackListInput[] = []
    for (const summary of summaries) {
      const vocabulary = await tracks.getTrackVocabulary(summary.id)
      if (!vocabulary) continue
      inputs.push({
        summary,
        vocabulary,
        lexicon: await tracks.lexiconFor(summary.id),
      })
    }

    // Live state, not what the file thought when it was written.
    const [carded, marked] = await Promise.all([
      cards.listCardedLemmas(),
      known.listAll(),
    ])
    const full = await cards.getMany([...carded])
    return buildTrackListView(inputs, buildKnownState(full.values(), marked))
  }, [tracks, cards, known, reloads])

  const onFile = useCallback(
    async (file: File) => {
      setBusy(true)
      setFailure(null)
      setDone(null)
      try {
        const outcome: ImportOutcome = await importFile(file, { known, tracks })
        setDone(describeImportSuccess(outcome))
        setReloads((n) => n + 1)
      } catch (error) {
        setFailure(describeImportFailure(error))
      } finally {
        setBusy(false)
      }
    },
    [known, tracks],
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

      {list.status === 'ready' && list.value.isEmpty && (
        <div className="text-ink-muted mt-16 text-center text-sm leading-relaxed text-balance">
          <p className="text-ink font-serif text-lg">Noch keine Lieder da.</p>
          <p className="mt-2">
            Lieder entstehen auf dem Rechner mit{' '}
            <span className="font-mono">build_track.py</span> und kommen per
            AirDrop hierher. Importieren, dann offline lesen.
          </p>
          <p className="mt-4">
            Derselbe Knopf nimmt auch eine{' '}
            <span className="font-mono">known.json</span> aus{' '}
            <span className="font-mono">seed_known.py</span> — dein
            Anki-Wortschatz, damit dir nichts beigebracht wird, was du längst
            kannst.
          </p>
        </div>
      )}

      {list.status === 'ready' && !list.value.isEmpty && (
        <ul className="divide-rule divide-y">
          {list.value.rows.map((row) => (
            <li key={row.id}>
              <button
                type="button"
                className="w-full py-4 text-left"
                onClick={() => navigate({ name: 'reader', trackId: row.id })}
              >
                <span className="font-serif block text-xl" lang="es">
                  {row.title}
                </span>
                <span className="text-ink-muted block text-sm">{row.artist}</span>
                <span className="text-ink-faint mt-1 block text-xs">
                  {[
                    cardsToLearn(row.cardsToLearn),
                    `${percent(row.coverage)} Abdeckung`,
                    row.dense ? 'dicht' : null,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Screen>
  )
}
