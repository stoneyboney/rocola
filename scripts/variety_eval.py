#!/usr/bin/env python3
"""SPEC §15 q2. Throwaway: nothing in `rocola_prep` imports this.

    uv run python scripts/variety_eval.py
    uv run python scripts/variety_eval.py --limit 20        # a quick look

> **Ollama over-tagging.** Expect the model to mark pan-Hispanic words as
> regional. Needs a held-out eval set of ~100 known-general lemmas to measure
> the false-positive rate before trusting `variety` in production.

## Two sets, and the second is the one §15 does not ask for

**Set A, false positives.** The commonest open-class Spanish lemmas, from
`wordfreq`. Frequency at that level is pan-Hispanic almost by definition: a word
in the top few thousand is a word every Spanish speaker has. Expect `general`;
count what gets tagged anyway.

**Set B, recall.** `molcajete_prep`'s shipped mexicanism gold list, plus
regionalisms from elsewhere in the Spanish-speaking world so the measurement is
not only about Mexico. Expect not-`general`.

Set B exists because **a tagger that answers `general` to everything scores a
perfect zero false positives and is useless**, and set A alone cannot tell the
difference. Phase 1's language filter was only believable because Dover proved
it could say no.

## No cache

`tag()` is called without one on purpose. A warm cache would measure the
previous run rather than the model.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from molcajete_prep.glossing.ollama import DEFAULT_MODEL  # noqa: E402
from molcajete_prep.glossing.provider import GlossTask  # noqa: E402
from molcajete_prep.nlp import load_pipeline  # noqa: E402

from rocola_prep.variety.models import Variety, VarietySense  # noqa: E402
from rocola_prep.variety.tagger import tag  # noqa: E402

#: Regionalisms from outside Mexico, so recall is not measured on one country.
#: Hand-written for this eval: reference data about Spanish, not a product rule,
#: and deliberately obvious cases — if these are missed, nothing subtler works.
NON_MEXICAN = [
    ("pibe", "NOUN", Variety.AR),
    ("laburo", "NOUN", Variety.AR),
    ("che", "INTJ", Variety.AR),
    ("boludo", "NOUN", Variety.AR),
    ("quilombo", "NOUN", Variety.AR),
    ("vale", "INTJ", Variety.ES),
    ("tío", "NOUN", Variety.ES),
    ("guay", "ADJ", Variety.ES),
    ("curro", "NOUN", Variety.ES),
    ("coger", "VERB", Variety.ES),
    ("chévere", "ADJ", Variety.VE),
    ("pana", "NOUN", Variety.VE),
    ("guagua", "NOUN", Variety.CU),
    ("jeva", "NOUN", Variety.PR),
    ("bregar", "VERB", Variety.PR),
    ("polola", "NOUN", Variety.CL),
    ("cachai", "VERB", Variety.CL),
    ("parcero", "NOUN", Variety.CO),
    ("chamba", "NOUN", Variety.PE),
    ("porotos", "NOUN", Variety.CL),
]

#: Closed-class tags never reach a card, so they never reach the tagger either.
CLOSED = {"ADP", "AUX", "CCONJ", "DET", "NUM", "PART", "PRON", "PUNCT", "SCONJ", "SYM", "X"}


@dataclass
class Scored:
    lemma: str
    pos: str
    expected_regional: bool
    expected_variety: Variety | None
    sense: VarietySense | None

    @property
    def answered(self) -> bool:
        return self.sense is not None

    @property
    def got_regional(self) -> bool:
        return self.sense is not None and self.sense.variety.is_regional

    @property
    def correct(self) -> bool:
        return self.answered and self.got_regional == self.expected_regional


def general_set(limit: int) -> list[tuple[str, str]]:
    """The commonest open-class Spanish lemmas. Expect `general`."""
    from wordfreq import top_n_list

    nlp = load_pipeline()
    picked: list[tuple[str, str]] = []
    seen: set[str] = set()

    # Walk deep: the top of the list is almost all closed-class, which is what
    # Phase 1's teach-set work found too.
    for word in top_n_list("es", 3000):
        if len(picked) >= limit:
            break
        if len(word) < 3 or not word.isalpha() or word in seen:
            continue
        doc = nlp(word)
        if not len(doc):
            continue
        token = doc[0]
        pos = token.pos_
        if pos in CLOSED or pos == "PROPN":
            continue
        lemma = token.lemma_.lower()
        if lemma in seen:
            continue
        seen.add(lemma)
        seen.add(word)
        picked.append((lemma, pos))
    return picked


def mexican_set() -> list[tuple[str, str]]:
    """`molcajete_prep`'s shipped gold list. Expect not-`general`."""
    from molcajete_prep import lexicon as _lexicon  # noqa: F401  (locate the package)

    path = (
        Path(_lexicon.__file__).resolve().parent / "data" / "mexicanisms.txt"
    )
    entries: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) == 2:
            entries.append((parts[0].strip(), parts[1].strip()))
    return entries


def run(entries: list[tuple[str, str, Variety | None]], model: str, label: str) -> list[Scored]:
    tasks = [GlossTask(lemma=lemma, pos=pos) for lemma, pos, _ in entries]
    print(f"\n{label}: {len(tasks)} lemmas…", file=sys.stderr, flush=True)

    result = tag(tasks, home_dialect=Variety.MX, model=model)

    scored: list[Scored] = []
    for lemma, pos, expected in entries:
        sense = result.senses.get((lemma, pos))
        scored.append(
            Scored(
                lemma=lemma,
                pos=pos,
                expected_regional=expected is not None,
                expected_variety=expected,
                sense=sense,
            )
        )
    return scored


def report(set_a: list[Scored], set_b: list[Scored], model: str) -> str:
    answered_a = [s for s in set_a if s.answered]
    answered_b = [s for s in set_b if s.answered]
    false_positives = [s for s in answered_a if s.got_regional]
    caught = [s for s in answered_b if s.got_regional]

    fp_rate = len(false_positives) / len(answered_a) if answered_a else 0.0
    recall = len(caught) / len(answered_b) if answered_b else 0.0

    lines = [
        f"# Variety tagging — over-tagging eval · {date.today().isoformat()}",
        "",
        f"SPEC §15 q2, against `{model}`. Home dialect `es-MX`. No cache: a warm",
        "one would measure the last run rather than the model.",
        "",
        "## The two numbers",
        "",
        "| | n | answered | tagged regional | |",
        "|---|---:|---:|---:|---|",
        f"| **A — expect `general`** | {len(set_a)} | {len(answered_a)} | "
        f"{len(false_positives)} | **{fp_rate:.0%} false positives** |",
        f"| **B — expect regional** | {len(set_b)} | {len(answered_b)} | "
        f"{len(caught)} | **{recall:.0%} recall** |",
        "",
    ]

    if false_positives:
        lines += [
            "## Set A — the ordinary words it tagged anyway",
            "",
            "| lemma | pos | got | confidence |",
            "|---|---|---|---:|",
        ]
        for s in sorted(false_positives, key=lambda s: s.lemma):
            assert s.sense
            conf = f"{s.sense.confidence:.2f}" if s.sense.confidence is not None else "—"
            lines.append(f"| {s.lemma} | {s.pos} | {s.sense.variety.value} | {conf} |")
        lines.append("")

    missed = [s for s in answered_b if not s.got_regional]
    if missed:
        lines += [
            "## Set B — the regionalisms it called general",
            "",
            "| lemma | pos | expected |",
            "|---|---|---|",
        ]
        for s in sorted(missed, key=lambda s: s.lemma):
            expected = s.expected_variety.value if s.expected_variety else "regional"
            lines.append(f"| {s.lemma} | {s.pos} | {expected} |")
        lines.append("")

    placed = [
        s for s in caught if s.expected_variety and s.sense
        and s.sense.variety is s.expected_variety
    ]
    lines += [
        "## Which variety, when it did tag one",
        "",
        f"Of {len(caught)} caught, **{len(placed)}** were placed in the country "
        "the gold list names.",
        "",
        "| answered | n |",
        "|---|---:|",
    ]
    got = Counter(s.sense.variety.value for s in caught if s.sense)
    for variety, n in got.most_common():
        lines.append(f"| {variety} | {n} |")

    stray = [
        s for s in answered_a
        if s.sense and s.sense.home_equivalent is not None
    ]
    lines += [
        "",
        "## Home equivalents where there should be none",
        "",
        f"{len(stray)} of {len(answered_a)} general senses came back carrying a "
        "`homeEquivalent`. All are stripped by `VarietySense.normalised` before "
        "storage; the count measures how hard the prompt is working against the "
        "model rather than with it.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int, default=100, help="size of set A")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    print("Building set A from wordfreq…", file=sys.stderr)
    a_entries = [(lemma, pos, None) for lemma, pos in general_set(args.limit)]
    b_entries = [(lemma, pos, Variety.MX) for lemma, pos in mexican_set()]
    b_entries += [(lemma, pos, variety) for lemma, pos, variety in NON_MEXICAN]

    print(f"  set A: {len(a_entries)} · set B: {len(b_entries)}", file=sys.stderr)

    set_a = run(a_entries, args.model, "Set A (expect general)")
    set_b = run(b_entries, args.model, "Set B (expect regional)")

    text = report(set_a, set_b, args.model)
    out = args.out or REPO / "reports" / f"variety-eval-{date.today().isoformat()}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")

    print("\n" + text)
    print(f"Wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
