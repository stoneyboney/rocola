"""last.fm client and the selection heuristic. SPEC §7.1.

Read-only, API key from local config and never committed. Paced, not
parallelised. The `nowplaying` entry in `getRecentTracks` is skipped — it has
no timestamp and reappears as a normal scrobble.
"""
