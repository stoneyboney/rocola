"""Dialect tagging and home-dialect rendering. SPEC §9.

`variety` defaults to `general`; over-tagging is the expected model failure
mode and when the provider is uncertain, `general` wins. `homeEquivalent` is
null when the home dialect uses the same word. Non-home-dialect forms are
recognition-only — never a production card (CLAUDE.md §5).
"""
