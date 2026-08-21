import type { GlossView } from '../domain/view/glossView'

/**
 * The tap-to-reveal sheet. SPEC §10.2.
 *
 * The interesting case is the missing German gloss: Wiktionary does not reach
 * 95% alone and the model half rejects lemmas it doubts, so "no gloss" is a
 * normal state the sheet has to say out loud rather than opening blank and
 * looking broken.
 *
 * The badge is here and not only on the card back, because this is the moment
 * the information is worth something — someone tapping `pibe` mid-song wants to
 * know it is Argentine now. It stays visually subordinate to the gloss
 * (CLAUDE.md §5): it is context, not the answer.
 */
export function GlossSheet({
  view,
  onClose,
}: {
  view: GlossView
  onClose: () => void
}) {
  return (
    <div
      className="bg-scrim fixed inset-0 z-10 flex items-end"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="bg-paper-raised border-rule w-full rounded-t-2xl border-t px-6 pt-5 pb-[max(1.5rem,env(safe-area-inset-bottom))]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-baseline gap-3">
          <h2 className="font-serif text-3xl" lang="es">
            {view.lemma}
          </h2>
          <span className="text-ink-faint text-xs tracking-wide uppercase">
            {view.pos}
          </span>
        </div>

        {view.de ? (
          <p className="mt-3 text-xl">{view.de}</p>
        ) : (
          <p className="text-ink-muted mt-3 text-base">
            Keine deutsche Übersetzung vorhanden.
          </p>
        )}
        {view.en && <p className="text-ink-muted mt-1 text-sm">{view.en}</p>}

        {(view.badge || view.register !== 'neutral') && (
          <p className="text-ink-faint mt-3 text-xs">
            {[view.badge, view.register !== 'neutral' ? view.register : null]
              .filter(Boolean)
              .join(' · ')}
            {view.homeEquivalent && (
              <span className="text-accent"> · MX: {view.homeEquivalent}</span>
            )}
          </p>
        )}

        {view.morphNote && (
          <p className="text-ink-muted mt-2 text-xs">{view.morphNote}</p>
        )}

        {view.example && (
          <p className="text-ink-muted border-rule mt-4 border-l-2 pl-3 text-sm" lang="es">
            {view.example}
          </p>
        )}

        <button
          type="button"
          onClick={onClose}
          className="border-rule mt-6 w-full rounded-xl border px-4 py-3 text-sm"
        >
          Schließen
        </button>
      </div>
    </div>
  )
}
