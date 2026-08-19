#!/usr/bin/env python3
"""Phase 1's measurement. Throwaway: nothing in `rocola_prep` imports this.

    uv run python scripts/coverage_probe.py --dry-run
    uv run python scripts/coverage_probe.py

SPEC §14: *"pull Spanish tracks from real last.fm history, run them through the
normaliser and the lookup ladder, and count hits. It is cheap and it changes the
plan."* The output is a report, not a feature.

## Two samples, and why

**Sample 1, context.** 12-month top tracks with the audio drama excluded. This
is what §7.1's playcount heuristic would actually hand you today, and the answer
turns out to be decision-relevant on its own.

**Sample 2, the measurement.** Every track by a seeded set of Hispanophone
artists, over `overall`. Playcount ranking cannot find this rotation — it is
thin and spread, a few plays across many tracks, all of it below any cut that
also admits the German music.

Seeding by artist is not classifying by artist. CLAUDE.md §10 forbids deciding
*language* from artist metadata, and nothing here does: the seed decides only
what is **worth probing**, and every language verdict in the report comes from
lingua running on the fetched text. Dover is seeded deliberately — a Spanish
band singing in English is the case §10 exists for, and if the filter cannot
reject them it is not working.

## No lyric text is retained

`plainLyrics` exists in this process as a local variable, long enough to be
measured and classified. It is never written, never logged, never put in the
report. The report holds counts.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from rocola_prep.config import describe, load_env  # noqa: E402
from rocola_prep.langfilter import detector  # noqa: E402
from rocola_prep.lastfm.client import LastfmClient, LastfmError, Track  # noqa: E402
from rocola_prep.lrclib.cache import ResolutionCache  # noqa: E402
from rocola_prep.lrclib.client import LrclibClient, Rung  # noqa: E402

# ---------------------------------------------------------------------------
# Sample 1's exclusion. Documented here and *only* here.
# ---------------------------------------------------------------------------
#
# `Die drei ???` is a German audio drama: one scrobble per Kapitel, ~50 per
# episode, 10,378 plays overall. It dominates every playcount ranking and it
# structurally cannot have lyrics, so leaving it in measures LRCLIB's coverage
# of an audiobook.
#
# This lives in the throwaway harness rather than in `rocola_prep` on purpose.
# Detecting "not music" is not in the spec, and CLAUDE.md §14 says ask rather
# than invent. It is written up as a Phase 2 question instead.
DRAMA_ARTISTS = {
    "die drei ???",
    "die drei ??? kids",
    "die drei fragezeichen",
    "tkkg",
    "offenbarung 23",
}
DRAMA_TITLE = re.compile(
    r"^(kapitel|teil|outro|intro|titelmusik|inhaltsangabe)\b|\(teil \d+\)$",
    re.IGNORECASE,
)

#: Sample 2's seed. Artists whose catalogue is worth *asking* about; the
#: language verdict still comes from the text. Dover is here on purpose.
SEED_ARTISTS = [
    "selena",
    "dover",
    "amaral",
    "chocolate remix",
    "juanes",
    "vicente fernández",
    "bad bunny",
    "molotov",
    "los bitchos",
    "ray lozano",
    # Found by scanning the artist list rather than from memory. Vicente
    # Fernández, Molotov and Ray Lozano are in the 12-month *artist* chart but
    # have no track-level rows in `overall` at all, so they contribute nothing
    # however deep the paging goes.
    "shakira",
    "café tacvba",
    "cafe tacvba",
    "shakira featuring wyclef jean",
]


def is_drama(track: Track) -> bool:
    return (
        track.artist.strip().lower() in DRAMA_ARTISTS
        or DRAMA_TITLE.search(track.title.strip()) is not None
    )


@dataclass
class Row:
    """One probed track. Carries counts, never text."""

    artist: str
    title: str
    playcount: int
    rung: Rung
    status: str
    score: float | None
    language: str | None
    confidence: float
    lang_verdict: str
    line_count: int
    char_count: int
    subset_collision: bool

    @property
    def is_spanish(self) -> bool:
        return self.lang_verdict == detector.Verdict.SPANISH.value


def collides(a: str, b: str) -> bool:
    """The §8.2 subset hazard: token sets equal or nested while strings differ.

    `token_set_ratio` scores 1.0 in this case, so `Ven Conmigo` matches the
    medley `Ven Conmigo / Perdóname` perfectly. Counted rather than prevented —
    changing the algorithm would be inventing where the spec is explicit.
    """
    sa, sb = set(a.split()), set(b.split())
    return a != b and (sa <= sb or sb <= sa)


def probe(tracks: list[Track], lrclib: LrclibClient, cache: ResolutionCache) -> list[Row]:
    rows: list[Row] = []
    for index, track in enumerate(tracks, 1):
        print(f"  [{index:>3}/{len(tracks)}] {track.artist} — {track.title}", flush=True)

        cached = cache.get(track.norm.key)
        if cached is not None and cached.status != "resolved":
            # A remembered miss. Nothing to classify, and §8.3 says do not
            # re-run the ladder for it.
            rows.append(
                Row(
                    track.artist, track.title, track.playcount, cached.rung,
                    cached.status, None, None, 0.0, "n/a", 0, 0, False,
                )
            )
            continue

        result = lrclib.resolve(
            track.title, track.artist, album=track.album, duration=track.duration
        )
        cache.put(result)

        lyrics = result.candidate.plain_lyrics if result.candidate else None
        classification = (
            detector.classify(lyrics)
            if result.resolved and lyrics
            else detector.Classification(detector.Verdict.TOO_SHORT, None, 0.0, {})
        )

        collision = False
        if result.candidate and result.score is not None:
            from rocola_prep.matcher.normalise import normalise

            other = normalise(result.candidate.track_name, result.candidate.artist_name)
            collision = collides(track.norm.title_key, other.title_key) or collides(
                track.norm.artist_key, other.artist_key
            )

        rows.append(
            Row(
                artist=track.artist,
                title=track.title,
                playcount=track.playcount,
                rung=result.rung,
                status=result.status,
                score=result.score.score if result.score else None,
                language=classification.language,
                confidence=classification.confidence,
                lang_verdict=classification.verdict.value,
                # Counts, not content. This is the only thing the lyric text is
                # used for besides classification, and then it goes out of scope.
                line_count=len([ln for ln in lyrics.splitlines() if ln.strip()]) if lyrics else 0,
                char_count=len(lyrics) if lyrics else 0,
                subset_collision=collision,
            )
        )
    return rows


def table(rows: list[Row]) -> str:
    total = len(rows)
    if total == 0:
        return "_No tracks in this sample._\n"

    by_rung = Counter(r.rung for r in rows)
    resolved = [r for r in rows if r.status == "resolved"]
    spanish = [r for r in resolved if r.is_spanish]

    out = [
        f"- **{total}** tracks probed",
        f"- **{len(resolved)}** resolved ({len(resolved) / total:.0%})",
        f"- **{len(spanish)}** confirmed Spanish by the text "
        f"({len(spanish) / total:.0%} of the sample)",
        "",
        "| rung | what it is | n | share |",
        "|---|---|---:|---:|",
    ]
    labels = {
        Rung.EXACT_FULL: "`/api/get` + album + duration",
        Rung.EXACT_LOOSE: "`/api/get`, loose",
        Rung.SEARCH_FIELDED: "`/api/search` fielded, scored",
        Rung.SEARCH_FREEFORM: "`/api/search?q=`, scored",
        Rung.EXHAUSTED: "nothing matched",
        Rung.CACHED: "from cache",
    }
    for rung in [
        Rung.EXACT_FULL, Rung.EXACT_LOOSE, Rung.SEARCH_FIELDED,
        Rung.SEARCH_FREEFORM, Rung.EXHAUSTED, Rung.CACHED,
    ]:
        n = by_rung.get(rung, 0)
        if n:
            out.append(f"| {int(rung)} | {labels[rung]} | {n} | {n / total:.0%} |")

    statuses = Counter(r.status for r in rows)
    out += ["", "| outcome | n |", "|---|---:|"]
    for status, n in statuses.most_common():
        out.append(f"| {status} | {n} |")

    langs = Counter(r.lang_verdict for r in resolved)
    out += ["", "| language verdict | n |", "|---|---:|"]
    for verdict, n in langs.most_common():
        out.append(f"| {verdict} | {n} |")

    collisions = [r for r in rows if r.subset_collision and r.status == "resolved"]
    out += [
        "",
        f"**Subset collisions among accepted matches: {len(collisions)}** "
        "— where §8.2's token-set ratio scored 1.0 because one side's tokens "
        "nest inside the other's. Each is a possible wrong-lyrics attachment.",
    ]
    return "\n".join(out) + "\n"


def by_artist(rows: list[Row]) -> str:
    """Coverage per artist.

    The cut that actually answers "can LRCLIB serve my Spanish rotation" — an
    aggregate mixes an English-singing Spanish band and an instrumental cumbia
    group in with the rest and reports a number that describes neither.
    """
    artists: dict[str, list[Row]] = {}
    for row in rows:
        artists.setdefault(row.artist, []).append(row)

    lines = [
        "| artist | n | resolved | es-confirmed | missed |",
        "|---|---:|---:|---:|---:|",
    ]
    for artist, group in sorted(artists.items(), key=lambda kv: -len(kv[1])):
        resolved = sum(1 for r in group if r.status == "resolved")
        spanish = sum(1 for r in group if r.is_spanish)
        missed = sum(1 for r in group if r.status == "no_lyrics")
        lines.append(
            f"| {artist} | {len(group)} | {resolved} | {spanish} | {missed} |"
        )
    return "\n".join(lines) + "\n"


def listing(rows: list[Row], predicate, heading: str) -> str:
    chosen = [r for r in rows if predicate(r)]
    if not chosen:
        return f"### {heading}\n\n_None._\n"
    lines = [f"### {heading} ({len(chosen)})", "", "| artist | title | rung | score |", "|---|---|---|---:|"]
    for r in sorted(chosen, key=lambda r: (-r.playcount, r.artist)):
        score = f"{r.score:.2f}" if r.score is not None else "—"
        lines.append(f"| {r.artist} | {r.title} | {int(r.rung)} | {score} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="select, do not fetch")
    parser.add_argument("--limit", type=int, default=150, help="sample 1 size")
    parser.add_argument("--seed-artist", action="append", default=[], metavar="NAME")
    parser.add_argument(
        "--pages", type=int, default=6, help="pages of 1000 to walk for sample 2"
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    env = load_env()
    print(f"LASTFM_API_KEY: {describe(env, 'LASTFM_API_KEY')}")
    print(f"LASTFM_USER:    {env.get('LASTFM_USER') or 'missing'}")
    try:
        lastfm = LastfmClient(env.get("LASTFM_API_KEY", ""), env.get("LASTFM_USER", ""))
    except LastfmError as exc:
        print(f"\n{exc}", file=sys.stderr)
        print("Create one at https://www.last.fm/api/account/create", file=sys.stderr)
        return 2

    seeds = {s.lower() for s in SEED_ARTISTS + args.seed_artist}

    print("\nSample 1: 12-month top tracks, audio drama excluded…")
    twelve = lastfm.top_tracks("12month", 1000)
    sample1 = [t for t in twelve if not is_drama(t)][: args.limit]
    print(f"  {len(twelve)} returned, {len(twelve) - len([t for t in twelve if not is_drama(t)])} drama rows dropped, {len(sample1)} kept")

    print("\nSample 2: artist-seeded Spanish pool over 'overall'…")
    # Paged deeply on purpose. `Die drei ???` alone is 10,378 plays across
    # hundreds of chapter rows, which pushes the Spanish rotation — a few plays
    # each, spread thin — well past the first page of 1000.
    overall = lastfm.top_tracks("overall", 1000, max_pages=args.pages)
    sample2 = [t for t in overall if t.artist.strip().lower() in seeds]
    print(f"  {len(overall)} returned, {len(sample2)} by the {len(seeds)} seeded artists")
    found = sorted({t.artist for t in sample2})
    print(f"  artists present: {', '.join(found) if found else '(none)'}")

    if args.dry_run:
        print("\n--dry-run: stopping before LRCLIB.")
        return 0

    cache = ResolutionCache(REPO / "cache" / "lrclib.sqlite3")
    lrclib = LrclibClient()

    print(f"\nProbing sample 1 ({len(sample1)} tracks)…")
    rows1 = probe(sample1, lrclib, cache)
    print(f"\nProbing sample 2 ({len(sample2)} tracks)…")
    rows2 = probe(sample2, lrclib, cache)
    cache.close()

    out = args.out or REPO / "reports" / f"coverage-probe-{date.today().isoformat()}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "\n".join(
            [
                f"# LRCLIB coverage probe — {date.today().isoformat()}",
                "",
                "Phase 1 of SPEC §14. Contains counts only: no lyric text reaches",
                "this file, by construction.",
                "",
                "## Sample 1 — what §7.1's heuristic selects",
                "",
                "12-month top tracks, audio drama excluded, capped at "
                f"{args.limit}.",
                "",
                table(rows1),
                "",
                listing(rows1, lambda r: r.is_spanish, "Spanish tracks in this sample"),
                "",
                "## Sample 2 — the Spanish rotation",
                "",
                "Every track by the seeded Hispanophone artists, over `overall`.",
                "",
                table(rows2),
                "",
                "### Per artist",
                "",
                by_artist(rows2),
                "",
                listing(rows2, lambda r: r.status == "no_lyrics", "Misses"),
                "",
                listing(rows2, lambda r: r.status == "review", "Fuzzy queue (0.70–0.85)"),
                "",
                listing(rows2, lambda r: r.subset_collision, "Subset collisions"),
                "",
                listing(
                    rows2,
                    lambda r: r.status == "resolved" and not r.is_spanish,
                    "Resolved but not Spanish by the text",
                ),
            ]
        )
    )
    print(f"\nReport: {out}")
    print("\n=== SAMPLE 1 ===")
    print(table(rows1))
    print("=== SAMPLE 2 ===")
    print(table(rows2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
