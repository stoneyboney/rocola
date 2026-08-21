import { useCallback, useEffect, useRef, useState } from 'react'
import { useRepositories } from '../app/repositories'
import { HOME } from '../app/routes'
import { useAsync } from '../app/useAsync'
import { useGoBack } from '../app/useRoute'
import { buildKnownState } from '../domain/knownLemmas'
import { computeCoverage } from '../domain/coverage'
import { selectTeachSet } from '../domain/teachSet'
import { buildGlossView, type GlossView } from '../domain/view/glossView'
import { buildReaderView, type ReaderView } from '../domain/view/readerView'
import type { LemmaKey, LexiconEntry, Variety } from '../domain/types'
import type { Track } from '../domain/track'
import { cardsToLearn, coverageNote, percent } from './format'
import { GlossSheet } from './GlossSheet'
import { Line } from './Line'
import { Screen } from './Screen'

interface Loaded {
  track: Track
  view: ReaderView
  lexicon: Map<LemmaKey, LexiconEntry>
  homeDialect: Variety
  cards: number
  coverage: number
  startAtLine: number
}

/**
 * A song. SPEC §10.
 *
 * ## The whole lexicon is read before the first line renders
 *
 * One bulk read, so the gloss sheet and the reveal-all toggle are synchronous.
 * That is what keeps a loading state out of the middle of a stanza and lets the
 * components stay dumb. Molcajete did the same for a chapter's slice; a song's
 * lexicon is fifty entries and the argument only gets easier.
 *
 * ## One tap handler for the whole song
 *
 * Delegated to the article. Words carry `data-t` and nothing else carries it,
 * so the target either has a lexicon key or the tap was on text. This is also
 * why `readerView` merges untappable tokens into text runs — punctuation never
 * becomes an element, so it can never be a target.
 *
 * ## Reveal-all is CSS, not state
 *
 * The `<ruby>` annotation is in the DOM for every glossOnly word that has a
 * German gloss, and one attribute on the article reveals them all. Making it a
 * React prop would re-render every line on a toggle press. It deliberately does
 * not persist across songs (§10.2 — it is for a second pass).
 */
export function Reader({ trackId }: { trackId: string }) {
  const { tracks, positions, cards, known, clock } = useRepositories()
  const goBack = useGoBack(HOME)

  const [revealAll, setRevealAll] = useState(false)
  const [gloss, setGloss] = useState<GlossView | null>(null)
  const article = useRef<HTMLElement>(null)

  const loaded = useAsync<Loaded | null>(async () => {
    const track = await tracks.getTrack(trackId)
    if (!track) return null

    const [stanzas, lexicon, vocabulary, position] = await Promise.all([
      tracks.getStanzas(trackId),
      tracks.lexiconFor(trackId),
      tracks.getTrackVocabulary(trackId),
      positions.get(trackId),
    ])

    const [carded, marked] = await Promise.all([
      cards.listCardedLemmas(),
      known.listAll(),
    ])
    const full = await cards.getMany([...carded])
    const state = buildKnownState(full.values(), marked)

    // Recomputed against live state, never read from the file. And each from
    // its own denominator: cards over unique lines, coverage over every line.
    const teach = vocabulary
      ? selectTeachSet(vocabulary.unique.counts, lexicon, new Set([...state.known, ...state.carded]))
      : { teach: [] as LemmaKey[], glossOnly: [] as LemmaKey[] }
    const coverage = vocabulary
      ? computeCoverage(vocabulary.all, lexicon, state.known)
      : 0

    return {
      track,
      view: buildReaderView(stanzas, teach.glossOnly, lexicon),
      lexicon,
      homeDialect: track.homeDialect,
      cards: teach.teach.length,
      coverage,
      startAtLine: position?.lineIndex ?? 0,
    }
  }, [tracks, positions, cards, known, trackId])

  const value = loaded.status === 'ready' ? loaded.value : null

  // Restore where you were. A line index rather than pixels, so it survives a
  // type-size change — and `scrollIntoView` rather than a stored offset for the
  // same reason.
  useEffect(() => {
    if (!value || value.startAtLine === 0) return
    const target = article.current?.querySelector(
      `[data-line="${value.startAtLine}"]`,
    )
    target?.scrollIntoView({ block: 'center' })
  }, [value])

  // Remember it. Whichever line is nearest the top of the viewport wins.
  useEffect(() => {
    if (!value) return
    const node = article.current
    if (!node) return

    let frame = 0
    const onScroll = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        const lines = node.querySelectorAll<HTMLElement>('[data-line]')
        for (const line of lines) {
          if (line.getBoundingClientRect().bottom > 0) {
            void positions.save(
              value.track.id,
              Number(line.dataset.line),
              clock.now(),
            )
            return
          }
        }
      })
    }

    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('scroll', onScroll)
    }
  }, [value, positions, clock])

  const onTap = useCallback(
    (event: React.MouseEvent<HTMLElement>) => {
      const target = (event.target as HTMLElement).closest<HTMLElement>('[data-t]')
      const key = target?.dataset.t
      if (!key || !value) return
      // The home dialect comes from the track, never a constant: it decides
      // whether a badge is shown at all (§9.2, CLAUDE.md §5).
      setGloss(buildGlossView(key, value.lexicon.get(key), value.homeDialect))
    },
    [value],
  )

  if (loaded.status !== 'ready') {
    return <Screen title="" back={{ label: 'Lieder', onClick: goBack }}>{null}</Screen>
  }

  if (!value) {
    return (
      <Screen title="Nicht gefunden" back={{ label: 'Lieder', onClick: goBack }}>
        <p className="text-ink-muted text-sm">Dieses Lied ist nicht mehr da.</p>
      </Screen>
    )
  }

  const warning = coverageNote(value.coverage)

  return (
    <Screen
      title={value.track.title}
      back={{ label: 'Lieder', onClick: goBack }}
      action={
        <button
          type="button"
          onClick={() => setRevealAll((on) => !on)}
          aria-pressed={revealAll}
          className="border-rule rounded-full border px-3 py-1.5 text-xs aria-pressed:bg-accent aria-pressed:text-white"
        >
          Übersetzungen
        </button>
      }
    >
      <p className="text-ink-muted -mt-2 text-sm">{value.track.artist}</p>
      <p className="text-ink-faint mt-1 text-xs">
        {[
          cardsToLearn(value.cards),
          `${percent(value.coverage)} Abdeckung`,
          value.track.dense ? 'dicht' : null,
        ]
          .filter(Boolean)
          .join(' · ')}
      </p>
      {/* A soft warning. CLAUDE.md §7: never a gate, never a lock. */}
      {warning && <p className="text-ink-muted mt-2 text-xs">{warning}</p>}

      <article
        ref={article}
        className="lyrics mt-8"
        data-reveal={revealAll ? 'true' : 'false'}
        onClick={onTap}
      >
        {value.view.stanzas.map((stanza) => (
          <section
            key={stanza.index}
            className="lyric-stanza"
            data-repeat={stanza.isRepeat ? 'true' : 'false'}
          >
            {stanza.lines.map((line) => (
              <Line key={line.index} view={line} />
            ))}
          </section>
        ))}
      </article>

      {gloss && <GlossSheet view={gloss} onClose={() => setGloss(null)} />}
    </Screen>
  )
}
