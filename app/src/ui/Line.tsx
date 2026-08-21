import { memo } from 'react'
import type { LineView } from '../domain/view/readerView'

/**
 * One line. Memoised, and given a view model it never recomputes: the runs, the
 * dotted underline and the reveal gloss are all decided in the domain layer.
 *
 * No `onClick` here. The handler is delegated to the article above — one
 * listener rather than one closure per word — which also means punctuation can
 * never be a tap target, because it never becomes an element.
 *
 * The reveal gloss is always in the DOM when it exists, hidden by CSS. That is
 * what makes the toggle a single attribute flip on the article rather than a
 * re-render of every line.
 */
export const Line = memo(function Line({ view }: { view: LineView }) {
  return (
    <p className="lyric-line" data-line={view.index} lang="es">
      {view.runs.map((run, index) => {
        if (run.kind === 'text') return run.text
        if (run.reveal !== null) {
          return (
            <ruby key={index} data-t={run.key} className="word word-marked">
              {run.text}
              <rt>{run.reveal}</rt>
            </ruby>
          )
        }
        return (
          <span
            key={index}
            data-t={run.key}
            className={run.marked ? 'word word-marked' : 'word'}
          >
            {run.text}
          </span>
        )
      })}
    </p>
  )
})
