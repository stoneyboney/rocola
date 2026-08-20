"""SPEC §7.5's pass: cache first, model for the rest, write through as it goes.

This is the *only* model pass Rocola runs. §7.5's answer carries `glossDe` and
`glossEn` alongside the dialect fields, so the glossing and the tagging are one
question — `build_track` runs `gloss_lexicon` with `use_model=False` for the
free Wiktionary half and lets this do the rest.

## Write-through is not an optimisation

`on_written` persists each chunk as it lands rather than at the end. The reason
is written down in `molcajete_prep`'s provider and is worth repeating: a run
that persisted only on completion lost two thousand glosses and about an hour
of compute to a single interruption. Since the cache is consulted before the
provider is called, writing as we go also makes an interrupted run resume where
it stopped rather than start again.

At 0.19 lemmas/sec — the rate measured on gemma3:12b on an M4 Pro — a hundred
lemmas is nine minutes. That is long enough to be interrupted.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from molcajete_prep.glossing.ollama import DEFAULT_MODEL, OllamaProvider
from molcajete_prep.glossing.provider import GlossTask

from rocola_prep.variety.cache import Identity, VarietyCache
from rocola_prep.variety.models import Variety, VarietySense
from rocola_prep.variety.prompts import (
    PROMPT_VERSION,
    VARIETY_SCHEMA,
    VarietyParser,
    build_system_prompt,
    render_correction,
)


@dataclass
class TagResult:
    senses: dict[Identity, VarietySense]
    from_cache: int = 0
    from_model: int = 0
    failed: int = 0

    @property
    def regional(self) -> dict[Identity, VarietySense]:
        return {k: v for k, v in self.senses.items() if v.variety.is_regional}


def build_provider(
    *,
    home_dialect: Variety,
    model: str,
    transport: Any = None,
    concurrency: int = 2,
    retries: int = 1,
) -> tuple[OllamaProvider, VarietyParser]:
    """A shared `OllamaProvider` asking §7.5's question instead of its own.

    Everything about the model being unreliable — the stricter retry, matching
    answers by echoed identity, the write-through — is inherited. Only the
    question is ours.
    """
    parser = VarietyParser(home_dialect=home_dialect)
    provider = OllamaProvider(
        model=model,
        concurrency=concurrency,
        retries=retries,
        transport=transport,
        system_prompt=build_system_prompt(home_dialect),
        schema=VARIETY_SCHEMA,
        render_retry=render_correction,
        parse_item=parser,
    )
    return provider, parser


def tag(
    tasks: Sequence[GlossTask],
    *,
    home_dialect: Variety = Variety.MX,
    model: str = DEFAULT_MODEL,
    cache_path: Path | str | None = None,
    cache: VarietyCache | None = None,
    transport: Any = None,
    on_status: Any = None,
) -> TagResult:
    """Tag every task, consulting the cache first.

    `cache_path` of None and no `cache` means run without one, which is what
    the eval does — it is measuring the model, and a warm cache would measure
    the last run instead.
    """
    owned = False
    if cache is None and cache_path is not None:
        cache = VarietyCache(
            cache_path,
            model=model,
            prompt_version=PROMPT_VERSION,
            home_dialect=home_dialect,
        )
        owned = True

    try:
        identities = [task.identity for task in tasks]
        cached = cache.get_many(identities) if cache else {}
        missing = [task for task in tasks if task.identity not in cached]

        senses: dict[Identity, VarietySense] = dict(cached)
        from_model = 0

        if missing:
            provider, parser = build_provider(
                home_dialect=home_dialect, model=model, transport=transport
            )

            def on_written(_batch: Any) -> None:
                # The parser has already recorded everything it parsed; persist
                # whatever is new rather than waiting for the pass to finish.
                if cache is not None:
                    for identity, sense in parser.senses.items():
                        if identity not in senses:
                            cache.put(sense)
                senses.update(parser.senses)

            provider.gloss(missing, on_status=on_status, on_written=on_written)

            # The callback fires per chunk; this catches anything a provider
            # implementation returned without announcing.
            for identity, sense in parser.senses.items():
                if identity not in senses and cache is not None:
                    cache.put(sense)
            senses.update(parser.senses)
            from_model = len(parser.senses)

        return TagResult(
            senses=senses,
            from_cache=len(cached),
            from_model=from_model,
            failed=len(missing) - from_model,
        )
    finally:
        if owned and cache is not None:
            cache.close()
