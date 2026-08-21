/**
 * Routing, by hand, over the location hash.
 *
 * A handful of screens do not need a router library. Hash routes also sit
 * correctly under the GitHub Pages sub-path and behind the service worker
 * without a navigateFallback rule having to guess which paths are the app's —
 * a deep link is one document plus a fragment, offline included.
 *
 * Three routes. Molcajete had five, and they encoded `/book/<id>/ch/<n>` —
 * both the book and the chapter are gone (SPEC §3). A song needs one segment,
 * because §11.1 says one song is one session and a song is never split, so
 * there is no second axis to put in a path.
 */

export type Route =
  | { name: 'home' }
  /** SPEC §6.5: due cards across every song. Carries nothing — what is due
   * is a question about the clock, asked on arrival. */
  | { name: 'review' }
  | { name: 'reader'; trackId: string }

export const HOME: Route = { name: 'home' }

/** Anything unrecognised falls back to the home screen rather than a dead one. */
export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#\/?/, '')
  if (path === 'wiederholen') return { name: 'review' }

  const parts = path.split('/').map(decodeURIComponent)
  if (parts.length === 2 && parts[0] === 'lied' && parts[1]) {
    return { name: 'reader', trackId: parts[1] }
  }

  return HOME
}

export function routeToHash(route: Route): string {
  switch (route.name) {
    case 'home':
      return '#/'
    case 'review':
      return '#/wiederholen'
    case 'reader':
      return `#/lied/${encodeURIComponent(route.trackId)}`
  }
}
