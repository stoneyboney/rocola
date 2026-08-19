"""Scrobble to LRCLIB. SPEC §8 — the highest-risk component.

Normalisation is for comparison only; the original scrobble strings are always
what gets displayed. Parenthetical stripping is stop-list driven. Nothing below
0.85 is auto-accepted: a wrong lyric silently attached to a track is worse than
no lyric at all.
"""
