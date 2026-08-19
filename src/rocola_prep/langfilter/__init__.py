"""Is this Spanish? SPEC §7.3.

Judged on the lyric text, never on last.fm artist tags, which are noisy and
mishandle bilingual artists. Local classifier only. Below the confidence
threshold goes to manual review, not to silent rejection.
"""
