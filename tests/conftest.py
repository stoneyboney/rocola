from __future__ import annotations

# Deliberately almost empty.
#
# `nlp`, `extracts`, `no_real_extracts` and `no_shared_cache` are not defined
# here. They come from molcajete-prep's pytest plugin, registered through its
# `pytest11` entry point, because every consumer of that package needs exactly
# the same guards — the ones that stop a test streaming 22.9 GB of Wiktionary
# or writing the developer's real gloss cache — and two copies of a guard is
# one copy too many. See `molcajete_prep/pytest_plugin.py`.
#
# Rocola's own fixtures land here as the pipeline is built. Per CLAUDE.md §2
# they use synthetic Spanish written for the test; no fixture in this repo may
# ever contain real lyric text.
