#!/usr/bin/env python3
"""One song in, one teach set out. SPEC §14's Phase 2 output.

    uv run python scripts/build_track.py --artist Selena --title "Como La Flor"
    uv run python scripts/build_track.py --artist Amaral --title "Sin Ti No Soy Nada" --gloss-offline

The whole pipeline end to end, for one track:

    §8   fetch plain lyrics through the lookup ladder, cached
    §7.3 classify the language on the text, never on the artist
    §7.4 stanzas, unique lines, teach set
    §7.5 gloss and variety, in one model pass

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
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from molcajete_prep.glossing.pipeline import GlossingOptions, gloss_lexicon  # noqa: E402
from molcajete_prep.glossing.provider import GlossTask  # noqa: E402
from molcajete_prep.lexicon import example_sentence  # noqa: E402
from molcajete_prep.nlp import load_pipeline  # noqa: E402

from rocola_prep.langfilter import detector  # noqa: E402
from rocola_prep.lrclib.cache import ResolutionCache  # noqa: E402
from rocola_prep.lrclib.client import LrclibClient  # noqa: E402
from rocola_prep.teachset.builder import classify_song, prepare  # noqa: E402
from rocola_prep.teachset.stanzas import parse_document  # noqa: E402
from rocola_prep.variety.models import Variety, parse_variety  # noqa: E402
from rocola_prep.variety.tagger import tag as tag_varieties  # noqa: E402


def track_id(artist: str, title: str) -> str:
    """A stable, filesystem-safe id. Also `gloss_lexicon`'s cache scope."""
    slug = f"{artist}-{title}"
    slug = unicodedata.normalize("NFKD", slug)
    slug = "".join(c for c in slug if not unicodedata.combining(c)).lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", slug)).strip("-")


def token_json(token, lexicon) -> dict:
    """One token, in the shape the reader has always consumed.

    Ported from Molcajete's `bundle.py` rather than re-derived: `{s, ws}` for
    whitespace, `{s, p}` for punctuation and numerals, `{s, l, p}` for a word,
    and `t` only when the token points at a lexicon entry. A proper noun has a
    lemma and no `t`, which is what makes it untappable in the reader for free.
    """
    if token.is_whitespace:
        return {"s": token.surface, "ws": True}

    entry: dict = {"s": token.surface, "p": lexicon.effective_pos(token)}
    if not token.is_word or token.lemma is None:
        # `l` would only repeat `s`.
        return entry

    entry["l"] = token.lemma
    key = lexicon.key_for(token)
    if key is not None:
        entry["t"] = key
    return entry


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
        "--home-dialect",
        default="es-MX",
        help="the reader's own Spanish (SPEC §6.4). Governs every regional "
        "judgement, and is part of the variety cache key — switching it is a "
        "re-gloss, not a re-render.",
    )
    parser.add_argument(
        "--no-variety",
        action="store_true",
        help="skip §7.5's dialect pass. Glosses come from Wiktionary only.",
    )
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

    # ---- §7.5: Wiktionary, then the one model pass ----------------------
    #
    # `use_model=False` on purpose. §7.5's answer carries glossDe and glossEn
    # alongside the dialect fields, so the variety pass *is* the model pass —
    # letting `gloss_lexicon` run its own would ask the same model about the
    # same lemmas twice to fill in one record.
    identifier = track_id(args.artist, args.title)
    glossing = gloss_lexicon(
        prepared.lexicon,
        prepared.song,
        # Structurally a cache scope. Molcajete passes a book here; Rocola
        # passes a song, which is the same thing wearing different clothes.
        book_id=identifier,
        options=GlossingOptions(use_model=False),
    )
    print(f"Wiktionary glossed {len(glossing.glosses)} lemmas", file=sys.stderr)

    home_dialect = parse_variety(args.home_dialect)
    senses: dict = {}
    if not args.gloss_offline and not args.no_variety:
        records = prepared.lexicon.records
        tasks = [
            GlossTask(
                lemma=record.lemma,
                pos=record.pos,
                example_es=(
                    found[0]
                    if (found := example_sentence(record, prepared.song))
                    else None
                ),
            )
            for record in records.values()
        ]
        result = tag_varieties(
            tasks,
            home_dialect=home_dialect,
            model=args.gloss_model,
            cache_path=REPO / "cache" / "variety.sqlite3",
        )
        senses = result.senses
        print(
            f"tagged {len(senses)} senses "
            f"({result.from_cache} from cache, {result.from_model} from the model), "
            f"{len(result.regional)} regional",
            file=sys.stderr,
        )

    def sense_for(key: str):
        record = prepared.lexicon.records.get(key)
        return senses.get((record.lemma, record.pos)) if record else None

    teach_set = classify_song(
        prepared,
        known_lemmas=load_known(args.known),
        # §5's teach rule promotes a regional word below the frequency floor.
        # Where Molcajete asks "is this Mexican", a pan-Hispanic rotation asks
        # "is this anyone's regionalism", which is what the tagger answers.
        mexicanism={
            key: sense.variety.is_regional
            for key in prepared.lexicon.records
            if (sense := sense_for(key)) is not None
        }
        or glossing.mexicanism_by_key(),
    )

    # ---- write ----------------------------------------------------------
    out = args.out or REPO / "tracks" / f"{identifier}.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    def lexicon_entry(key: str) -> dict:
        """One lexicon entry, for every key the song refers to.

        Every key, not only the taught ones. `glossOnly` words are the ones the
        reader taps and gets a gloss for without ever being carded — they were
        a list of keys pointing at nothing until now, which is why no gloss
        sheet could open.
        """
        record = prepared.lexicon.records[key]
        gloss = glossing.gloss_for(key)
        sense = senses.get((record.lemma, record.pos))
        found = example_sentence(record, prepared.song)
        # The model pass wins on the glosses: it saw the line the word occurs
        # in, and §7.5 asks for German first for exactly that reason.
        return {
            "lemma": record.lemma,
            "pos": record.pos,
            "zipf": round(record.zipf, 2),
            # Occurrences across UNIQUE lines. The teach set's denominator;
            # coverage counts over every line and gets its own numbers from
            # the tokens below. See the plan's two-denominator note.
            "uniqueLineCount": record.book_count,
            "example": found[0] if found else None,
            "de": (sense.de if sense else None) or (gloss.de if gloss else None),
            "en": (sense.en if sense else None) or (gloss.en if gloss else None),
            # SPEC §6.3. `variety` is `general` unless the model was sure; see
            # docs/phase2-variety-eval.md for how often that is right.
            "variety": sense.variety.value if sense else Variety.GENERAL.value,
            "register": sense.register.value if sense else "neutral",
            "homeEquivalent": sense.home_equivalent if sense else None,
            "homeEquivalentNote": sense.home_equivalent_note if sense else None,
            "morphNote": sense.morph_note if sense else None,
            "confidence": sense.confidence if sense else None,
            # §9.2: no badge for `general`, and none for the reader's own
            # dialect — in Monterrey a Monterrey word is just a word.
            "badge": (
                sense.variety.badge
                if sense and sense.needs_badge(home_dialect)
                else None
            ),
        }

    # Tokens for every line, repeats included: the reader renders the whole
    # song. `prepared.song` is the unique lines and is what the teach set was
    # counted over — the two are deliberately different and both are needed.
    tokens_by_line = {
        line.index: [token_json(tok, prepared.lexicon) for tok in tokens]
        for line, tokens in zip(document.lines, prepared.all_tokens, strict=True)
    }

    out.write_text(
        json.dumps(
            {
                # 2, not 1. A version-1 file has no tokens and no lexicon, so
                # nothing can render it — the app rejects it and says to rebuild.
                "schemaVersion": 2,
                "id": identifier,
                "artist": args.artist,
                "title": args.title,
                "homeDialect": home_dialect.value,
                "language": language.language,
                "languageConfidence": round(language.confidence, 3),
                "lrclibId": resolution.candidate.id,
                "rung": int(resolution.rung),
                # SPEC §6.2. `manual` arrives with §8.5's paste path.
                "source": "lrclib",
                "fetchedAt": datetime.now(timezone.utc).isoformat(),
                "stanzas": [
                    {
                        "index": stanza.index,
                        "repeatOf": stanza.repeat_of,
                        "lines": [
                            {
                                "index": line.index,
                                "text": line.text,
                                "repeatOf": line.repeat_of,
                                "tokens": tokens_by_line[line.index],
                            }
                            for line in stanza.lines
                        ],
                    }
                    for stanza in document.stanzas
                ],
                # `lexicon` is the single source; these two are key lists into
                # it. `teach` is a CLI diagnostic — **the app must not read it.**
                # It was computed against a known-set that was already stale
                # when the file was written, and the app recomputes from the
                # token counts against live state.
                "lexicon": {
                    key: lexicon_entry(key) for key in sorted(prepared.lexicon.records)
                },
                "teach": [entry.key for entry in teach_set.teach],
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
        sense = senses.get((entry.lemma, entry.pos))
        german = (sense.de if sense else None) or (gloss.de if gloss else None) or "—"
        badge = (
            f"  [{sense.variety.badge}]"
            if sense and sense.needs_badge(home_dialect)
            else ""
        )
        print(f"  {entry.unique_line_count:>2}x  {entry.lemma:<16} {german}{badge}")
    if len(teach_set.teach) > 25:
        print(f"  … and {len(teach_set.teach) - 25} more")
    print(f"\nWrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
