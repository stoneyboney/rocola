"""LRCLIB client. SPEC §7.2, §8.4.

Plain lyrics only: `syncedLyrics` is discarded even when returned (CLAUDE.md
§1). Sends a User-Agent naming the app. `instrumental: true` is a terminal
`no_lyrics` and is never retried. Every field is optional.
"""
