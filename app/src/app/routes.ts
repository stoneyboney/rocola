/**
 * Routing, by hand, over the location hash.
 *
 * A handful of screens do not need a router library. Hash routes also sit
 * correctly under the GitHub Pages sub-path and behind the service worker
 * without a navigateFallback rule having to guess which paths are the app's —
 * a deep link is one document plus a fragment, offline included.
 *
 * Two routes, where Molcajete had five. `chapters`, `reader` and `session` all
 * encoded `/book/<id>/ch/<n>`, and both the book and the chapter are gone
 * (SPEC §3). The song routes arrive in Phase 3 as `/lied/<trackId>`; until a
 * `Track` exists there is nothing honest to name in a path.
 */

export type Route =
  | { name: 'home' }
  /** SPEC §6.5: due cards across every song. Carries nothing — what is due
   * is a question about the clock, asked on arrival. */
  | { name: 'review' }

export const HOME: Route = { name: 'home' }

/** Anything unrecognised falls back to the home screen rather than a dead one. */
export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#\/?/, '')
  if (path === 'wiederholen') return { name: 'review' }
  return HOME
}

export function routeToHash(route: Route): string {
  switch (route.name) {
    case 'home':
      return '#/'
    case 'review':
      return '#/wiederholen'
  }
}
