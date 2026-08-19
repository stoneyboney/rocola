"""SPEC §7.3 — is this actually Spanish?

## Judged on the text, never on the artist

CLAUDE.md §10 is unambiguous and it is the rule with the most obvious
counter-temptation: last.fm knows the artist, artists have country tags, and
reading a tag is free where fetching lyrics is not. It is still wrong. Tags are
noisy and they mishandle exactly the artists that matter — Dover is a Spanish
band that sings in English, and any tag-based filter hands their entire
catalogue to a Spanish reader.

So the classifier runs **after** the fetch, on the lyric text, and the artist
never enters into it.

## Below the threshold is `review`, not `reject`

§7.3 again: *"A track at 0.6 Spanish is genuinely mixed; surface it to the user
as a manual-review item rather than auto-rejecting."* Spanglish is a real
register, not a classifier failure, and a filter that silently drops it removes
material the reader would actively want. `Verdict.REVIEW` exists so the
difference between "not Spanish" and "not confidently Spanish" survives into the
report.

## The candidate set, and the one member of it that does not exist

Restricting the set is what makes lingua sharp on short text: a song lyric is a
few hundred words, and a detector weighing all seventy-five of its languages
spends its confidence budget on Estonian.

SPEC §7.3 names seven — `{es, en, pt, ca, gl, it, fr}`. **lingua does not
support Galician.** It is not among the 75, and there is no flag that adds it.
So the set here is six, and the spec's seventh is recorded as unavailable rather
than quietly swapped for something else.

What that costs: Galician sits between Spanish and Portuguese and will be
classified as one of them. Portuguese is the likelier of the two, which puts a
Galician track in `OTHER` and out of the Spanish subset — a miss, not a false
positive, which is the safer direction to fail in. Basque *is* supported and
would be a defensible addition for a pan-Hispanic rotation, but it is not in
§7.3's list and adding it is a spec decision rather than an implementation one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache

from lingua import Language, LanguageDetector, LanguageDetectorBuilder

#: SPEC §7.3's candidate set, less Galician, which lingua does not have.
LANGUAGES = (
    Language.SPANISH,
    Language.ENGLISH,
    Language.PORTUGUESE,
    Language.CATALAN,
    Language.ITALIAN,
    Language.FRENCH,
)

#: Named in SPEC §7.3 and unavailable in lingua. Kept as a constant so the gap
#: is greppable rather than folded silently into the list above.
UNSUPPORTED_BY_LINGUA = ("gl",)

#: SPEC §6.4's `minLanguageConfidence`.
DEFAULT_MIN_CONFIDENCE = 0.80

#: Below this there is not enough text for any verdict to mean anything. A
#: two-line fragment classifies as whatever its function words look like.
MIN_CHARACTERS = 40

_ISO = {
    Language.SPANISH: "es",
    Language.ENGLISH: "en",
    Language.PORTUGUESE: "pt",
    Language.CATALAN: "ca",
    Language.ITALIAN: "it",
    Language.FRENCH: "fr",
}


class Verdict(str, Enum):
    SPANISH = "spanish"
    REVIEW = "review"
    """Spanish, but not confidently. §7.3: a manual-review item, not a reject."""
    OTHER = "other"
    TOO_SHORT = "too_short"


@dataclass(frozen=True)
class Classification:
    verdict: Verdict
    language: str | None
    confidence: float
    #: Every language's score, for the report. Diagnostic only.
    scores: dict[str, float]

    @property
    def is_spanish(self) -> bool:
        """Confidently Spanish. `REVIEW` is deliberately excluded."""
        return self.verdict is Verdict.SPANISH


@lru_cache(maxsize=1)
def _detector() -> LanguageDetector:
    """Built once. Construction loads models and is far from free."""
    return LanguageDetectorBuilder.from_languages(*LANGUAGES).build()


def classify(
    text: str, *, min_confidence: float = DEFAULT_MIN_CONFIDENCE
) -> Classification:
    """Classify lyric text. Never called with an artist name (CLAUDE.md §10)."""
    stripped = text.strip() if text else ""
    if len(stripped) < MIN_CHARACTERS:
        return Classification(Verdict.TOO_SHORT, None, 0.0, {})

    scores = {
        _ISO[value.language]: value.value
        for value in _detector().compute_language_confidence_values(stripped)
        if value.language in _ISO
    }
    if not scores:
        return Classification(Verdict.OTHER, None, 0.0, {})

    language, confidence = max(scores.items(), key=lambda kv: kv[1])

    if language != "es":
        return Classification(Verdict.OTHER, language, confidence, scores)
    if confidence >= min_confidence:
        return Classification(Verdict.SPANISH, "es", confidence, scores)
    return Classification(Verdict.REVIEW, "es", confidence, scores)
