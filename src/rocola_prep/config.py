"""Reading `.env`, in about twenty lines.

`python-dotenv` does this and more. The more is the reason it is not here: this
package needs two strings out of one file, the file format is `KEY=value`, and
a dependency that exists to parse that is a dependency to keep current forever.

CLAUDE.md §8: the last.fm key lives in local config and is **never committed**.
`.env` is gitignored and `.env.example` is the template that holds no value.
Nothing in this module logs, prints or repr's a value — callers that want to
report on configuration should report `present` / `missing`, which is what
`describe` is for.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Walk up from `src/rocola_prep/config.py` to the repo root.
_DEFAULT_ENV = Path(__file__).resolve().parents[2] / ".env"


def load_env(path: Path | str | None = None, *, overlay_os: bool = True) -> dict[str, str]:
    """Parse a `.env` into a dict.

    Understands what a `.env` actually contains and nothing else: `KEY=value`,
    blank lines, `#` comments, an optional `export ` prefix, and surrounding
    quotes. A line without `=` is skipped rather than raised on, because a
    malformed line in a config file should not stop a probe that may not even
    need the value.

    Real environment variables win by default, so `LASTFM_API_KEY=… uv run …`
    works without editing the file.
    """
    env_path = Path(path) if path is not None else _DEFAULT_ENV
    values: dict[str, str] = {}

    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.removeprefix("export ").strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if key:
                values[key] = value

    if overlay_os:
        for key in list(values) + ["LASTFM_API_KEY", "LASTFM_USER"]:
            if os.environ.get(key):
                values[key] = os.environ[key]

    return values


def describe(values: dict[str, str], key: str) -> str:
    """`set` or `missing` — never the value.

    Exists so that a probe can print what it is configured with without a
    credential ending up in a terminal buffer, a screenshot or a log file.
    """
    return "set" if values.get(key) else "missing"
