import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

// Served from https://<user>.github.io/rocola/ — a project page, so every
// asset URL needs the sub-path. `start_url` and `scope` below must agree with
// it or iOS launches the home-screen icon into a fresh browser context.
//
// This is also the service worker's scope, and it is the *only* thing about
// the two apps that is separated by path. IndexedDB and Cache Storage are not
// — see `workbox.cacheId` below and `infra/db.ts`. CLAUDE.md §3.
const BASE = '/rocola/'

export default defineConfig({
  base: BASE,
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      // No `includeAssets`: the icons live in public/ and the glob below
      // already precaches them. Listing them twice puts duplicate entries in
      // the precache manifest.
      manifest: {
        name: 'Rocola',
        short_name: 'Rocola',
        description: 'Songtexte auf Spanisch lesen, mit vorbereitetem Wortschatz.',
        lang: 'de',
        start_url: BASE,
        scope: BASE,
        display: 'standalone',
        orientation: 'portrait',
        background_color: '#f4f1f7',
        theme_color: '#f4f1f7',
        icons: [
          { src: 'icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          {
            src: 'icons/icon-512-maskable.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        // **Every Cache Storage key this app owns starts `rocola-`.**
        //
        // Cache Storage is scoped to the origin, and Molcajete is served from
        // the same one. Without `cacheId`, workbox names its caches
        // `workbox-precache-v2-<registration.scope>` — which happens to differ
        // between the two apps, but only because their scopes differ, and the
        // scope is the one thing here that *is* path-based. That accident stops
        // protecting anything the moment somebody adds a runtimeCaching rule
        // with an explicit cacheName. So the separation is stated rather than
        // inherited. CLAUDE.md §3.
        cacheId: 'rocola',
        // The app shell, and nothing else. Lyrics live in IndexedDB; caching
        // them here would give the cache a second, silently diverging copy.
        // There are deliberately no runtimeCaching rules — the reader makes no
        // runtime request to cache.
        globPatterns: ['**/*.{js,css,html,png,svg,woff2}'],
        navigateFallback: `${BASE}index.html`,
        cleanupOutdatedCaches: true,
      },
      devOptions: { enabled: false },
    }),
  ],
})
