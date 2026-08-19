"""SPEC §8.2's candidate scoring, and the three thresholds it feeds.

`/api/search` returns a list; this decides which of them, if any, is the track
that was actually scrobbled.

## Why the ratio is written out rather than imported

`rapidfuzz` has a `token_set_ratio` and it is faster than this one. Speed is
irrelevant here — a probe scores a few hundred candidates — and what is *not*
irrelevant is that §8.2's weights are a judgement call that will be retuned
against real misses. A scoring function whose core is somebody else's C++ is a
scoring function you tune by guessing. This one is twenty lines of `difflib`
and every number in it can be read.

## The verdicts, and why the middle one exists

    >= 0.85    accept
    0.70-0.85  queue for manual confirmation
    <  0.70    reject

CLAUDE.md §9: **never auto-accept below 0.85.** The band is not indecision, it
is the acknowledgement that a wrong lyric silently attached to a track is worse
than no lyric — the user studies vocabulary from a song they are not listening
to, and nothing downstream can detect it. A miss is visible; a mismatch is not.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum

TITLE_WEIGHT = 0.50
ARTIST_WEIGHT = 0.35
DURATION_WEIGHT = 0.15

ACCEPT_THRESHOLD = 0.85
REVIEW_THRESHOLD = 0.70

#: Seconds either side of the scrobbled duration that still earn full credit.
DURATION_TOLERANCE = 3.0


class Verdict(str, Enum):
    ACCEPT = "accept"
    REVIEW = "review"
    REJECT = "reject"


@dataclass(frozen=True)
class Scored:
    score: float
    verdict: Verdict
    title_similarity: float
    artist_similarity: float
    #: `None` when either side had no duration, in which case the weight was
    #: redistributed rather than scored as zero. Recorded so a report can say
    #: which matches were decided without it.
    duration_similarity: float | None


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def token_set_ratio(a: str, b: str) -> float:
    """Similarity that ignores word order and tolerates extra words.

    The rapidfuzz algorithm, written out. Split both into word sets, then
    compare three constructed strings:

        t0  the words they share, sorted
        t1  t0 + the words only `a` has
        t2  t0 + the words only `b` has

    and take the best of the three pairwise ratios. The point of `t0` is that a
    candidate carrying extra words — an album suffix, a second artist — still
    scores highly against the shorter side, because `t0` against `t1` measures
    only what the extra words cost.

    This is what makes `la bamba` and `bamba la` identical, and `corazon
    espinado` against `corazon espinado remasterizado` high rather than middling.
    """
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0

    shared = sorted(tokens_a & tokens_b)
    only_a = sorted(tokens_a - tokens_b)
    only_b = sorted(tokens_b - tokens_a)

    t0 = " ".join(shared)
    t1 = " ".join(shared + only_a).strip()
    t2 = " ".join(shared + only_b).strip()

    return max(_ratio(t0, t1), _ratio(t0, t2), _ratio(t1, t2))


def duration_similarity(
    scrobbled: float | None, candidate: float | None
) -> float | None:
    """1.0 within the tolerance, decaying to 0 by 30 s out. `None` if unknowable.

    SPEC §8.2 gives full credit within ±3 s and says to use the term *only if
    both are known*. Scrobbled durations are frequently absent and frequently
    wrong — a live version scrobbled against a studio length — so `None` here is
    common and must not be confused with "known, and completely different".
    """
    if scrobbled is None or candidate is None:
        return None
    if scrobbled <= 0 or candidate <= 0:
        return None

    delta = abs(scrobbled - candidate)
    if delta <= DURATION_TOLERANCE:
        return 1.0
    return max(0.0, 1.0 - (delta - DURATION_TOLERANCE) / 30.0)


def score_candidate(
    *,
    title_key: str,
    artist_key: str,
    candidate_title_key: str,
    candidate_artist_key: str,
    scrobbled_duration: float | None = None,
    candidate_duration: float | None = None,
) -> Scored:
    """SPEC §8.2's weighted score for one `/api/search` result.

    When the duration term is unavailable its weight is **redistributed across
    the other two in proportion**, not scored as zero. Scoring it zero would
    mean the best possible match on a track with no duration caps at 0.85 — the
    accept threshold exactly — and every such track would land in the manual
    queue for a reason that has nothing to do with how well it matched.
    """
    title_sim = token_set_ratio(title_key, candidate_title_key)
    artist_sim = token_set_ratio(artist_key, candidate_artist_key)
    duration_sim = duration_similarity(scrobbled_duration, candidate_duration)

    if duration_sim is None:
        total = TITLE_WEIGHT + ARTIST_WEIGHT
        score = (TITLE_WEIGHT * title_sim + ARTIST_WEIGHT * artist_sim) / total
    else:
        score = (
            TITLE_WEIGHT * title_sim
            + ARTIST_WEIGHT * artist_sim
            + DURATION_WEIGHT * duration_sim
        )

    return Scored(
        score=score,
        verdict=verdict_for(score),
        title_similarity=title_sim,
        artist_similarity=artist_sim,
        duration_similarity=duration_sim,
    )


def verdict_for(score: float) -> Verdict:
    if score >= ACCEPT_THRESHOLD:
        return Verdict.ACCEPT
    if score >= REVIEW_THRESHOLD:
        return Verdict.REVIEW
    return Verdict.REJECT
