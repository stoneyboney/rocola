#!/usr/bin/env python3
"""One song in, one teach set out. SPEC §14's Phase 2 output.

    uv run python scripts/build_track.py --artist Selena --title "Como La Flor"
    uv run python scripts/build_track.py --artist Amaral --title "Sin Ti No Soy Nada" --gloss-offline

The whole pipeline end to end, for one track:

    §8   fetch plain lyrics through the lookup ladder, cached
    §7.3 classify the language on the text, never on the artist
    §7.4 stanzas, unique lines, teach set
    §7.5 gloss — the German/English half only; variety tagging is not built

Glossing runs **between** building the lexicon and classifying it, because
`mexicanism && bookCount >= 2` is a teach rule and the flag has to exist before
the rules are applied. Molcajete's builder orders it the same way.

## Where the lyric text goes

Into `tracks/<id>.json`, which is gitignored.

SPEC §2 forbids lyric text **in the repository**; §12 forbids bundling or
redistributing it. A working file on the owner's own machine is neither — and
the pipeline being the thing that fetches is what keeps the inherited hard
constraint that the reader makes zero network calls at runtime.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from molcajete_prep.glossing.pipeline import GlossingOptions, gloss_lexicon  # noqa: E402
from molcajete_prep.glossing.provider import OLLAMA, ProviderOptions  # noqa: E402
from molcajete_prep.nlp import load_pipeline  # noqa: E402

from rocola_prep.langfilter import detector  # noqa: E402
from rocola_prep.lrclib.cache import ResolutionCache  # noqa: E402
from rocola_prep.lrclib.client import LrclibClient  # noqa: E402
from rocola_prep.teachset.builder import classify_song, prepare  # noqa: E402
from rocola_prep.teachset.stanzas import parse_document  # noqa: E402


def track_id(artist: str, title: str) -> str:
    """A stable, filesystem-safe id. Also `gloss_lexicon`'s cache scope."""
    slug = f"{artist}-{title}"
    slug = unicodedata.normalize("NFKD", slug)
    slug = "".join(c for c in slug if not unicodedata.combining(c)).lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", slug)).strip("-")


def load_known(path: Path | None) -> frozenset[str]:
    """A `known.json` — the flat array of lemma strings, same as Molcajete's."""
    if path is None or not path.is_file():
        return frozenset()
    data = json.loads(path.read_text(encoding="utf-8"))
    return frozenset(str(lemma).lower() for lemma in data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artist", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--album", default=None)
    parser.add_argument("--duration", type=float, default=None)
    parser.add_argument("--known", type=Path, default=REPO / "known.json")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--gloss-offline",
        action="store_true",
        help="Wiktionary and the cache only. No model, no waiting.",
    )
    parser.add_argument("--gloss-model", default="gemma3:12b")
    parser.add_argument(
        "--force-language",
        action="store_true",
        help="build even when the classifier says the lyrics are not Spanish",
    )
    args = parser.parse_args()

    # ---- §8: fetch ------------------------------------------------------
    cache = ResolutionCache(REPO / "cache" / "lrclib.sqlite3")
    resolution = LrclibClient().resolve(
        args.title, args.artist, album=args.album, duration=args.duration
    )
    cache.put(resolution)
    cache.close()

    print(f"rung {int(resolution.rung)}  {resolution.status}", file=sys.stderr)
    if not resolution.resolved or resolution.candidate is None:
        print(
            f"no lyrics for {args.artist} — {args.title}. "
            "SPEC §8.5's manual paste is the escape hatch; not built yet.",
            file=sys.stderr,
        )
        return 1

    lyrics = resolution.candidate.plain_lyrics
    assert lyrics is not None

    # ---- §7.3: language, on the text ------------------------------------
    language = detector.classify(lyrics)
    print(
        f"language {language.language} {language.confidence:.2f} "
        f"({language.verdict.value})",
        file=sys.stderr,
    )
    if not language.is_spanish and not args.force_language:
        print(
            "not confidently Spanish. §10 sends this to manual review rather "
            "than rejecting it — pass --force-language to build anyway.",
            file=sys.stderr,
        )
        return 2

    # ---- §7.4: stanzas and the lexicon ----------------------------------
    document = parse_document(lyrics)
    nlp = load_pipeline()
    prepared = prepare(document, nlp)
    print(
        f"{len(document.stanzas)} stanzas, {len(document.lines)} lines, "
        f"{len(document.unique_lines)} unique "
        f"({prepared.total_word_tokens} word tokens, "
        f"{prepared.unique_word_tokens} after deduplication)",
        file=sys.stderr,
    )

    # ---- §7.5: gloss, then classify -------------------------------------
    identifier = track_id(args.artist, args.title)
    glossing = gloss_lexicon(
        prepared.lexicon,
        prepared.song,
        # Structurally a cache scope. Molcajete passes a book here; Rocola
        # passes a song, which is the same thing wearing different clothes.
        book_id=identifier,
        options=GlossingOptions(
            use_model=not args.gloss_offline,
            provider_options=ProviderOptions(name=OLLAMA, model=args.gloss_model),
        ),
    )
    print(
        f"glossed {len(glossing.glosses)} lemmas "
        f"({glossing.cache_hits} from cache, {glossing.sent_to_model} to the model)",
        file=sys.stderr,
    )

    teach_set = classify_song(
        prepared,
        known_lemmas=load_known(args.known),
        mexicanism=glossing.mexicanism_by_key(),
    )

    # ---- write ----------------------------------------------------------
    out = args.out or REPO / "tracks" / f"{identifier}.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    def card(entry) -> dict:
        gloss = glossing.gloss_for(entry.key)
        return {
            "key": entry.key,
            "lemma": entry.lemma,
            "pos": entry.pos,
            "zipf": round(entry.zipf, 2),
            "uniqueLineCount": entry.unique_line_count,
            "example": entry.example,
            "de": gloss.de if gloss else None,
            "en": gloss.en if gloss else None,
            "regionNote": gloss.region_note if gloss else None,
            "mexicanism": bool(gloss and gloss.mexicanism),
        }

    out.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "id": identifier,
                "artist": args.artist,
                "title": args.title,
                "language": language.language,
                "languageConfidence": round(language.confidence, 3),
                "lrclibId": resolution.candidate.id,
                "rung": int(resolution.rung),
                "stanzas": [
                    {
                        "index": stanza.index,
                        "repeatOf": stanza.repeat_of,
                        "lines": [
                            {
                                "index": line.index,
                                "text": line.text,
                                "repeatOf": line.repeat_of,
                            }
                            for line in stanza.lines
                        ],
                    }
                    for stanza in document.stanzas
                ],
                "teach": [card(entry) for entry in teach_set.teach],
                "glossOnly": list(teach_set.gloss_only),
                "counts": {
                    "wordTokens": teach_set.total_word_tokens,
                    "uniqueWordTokens": teach_set.unique_word_tokens,
                    "deduplicationRatio": round(teach_set.deduplication_ratio, 3),
                    "teachCards": len(teach_set.teach),
                },
                # §11.1: surfaced for the reader to decide about. Never split.
                "dense": teach_set.is_dense,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\n{len(teach_set.teach)} cards" + ("  (dense)" if teach_set.is_dense else ""))
    for entry in teach_set.teach[:25]:
        gloss = glossing.gloss_for(entry.key)
        german = (gloss.de if gloss else None) or "—"
        print(f"  {entry.unique_line_count:>2}x  {entry.lemma:<16} {german}")
    if len(teach_set.teach) > 25:
        print(f"  … and {len(teach_set.teach) - 25} more")
    print(f"\nWrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
