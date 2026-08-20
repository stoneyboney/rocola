"""SPEC §7.5's question, and the parser that refuses to believe the answer.

This is the one model pass. §7.5's response schema is a superset of what a
gloss needs — it returns `glossDe` and `glossEn` alongside `variety` — so
Rocola does not gloss and then tag; it asks once.

## The home dialect is a parameter, not a constant

CLAUDE.md §5: `homeDialect` governs all regional rendering and is never
hard-coded. So the system prompt is *built*, not stored: `build_system_prompt`
names the reader's own Spanish in the instructions, because "is this word
regional" has no answer until you say regional *relative to what*.

## Guarding the failure mode we already know about

CLAUDE.md §5 and SPEC §7.5 both say the same thing in different words:
**over-tagging is the expected failure.** A model asked to spot regionalisms
will spot them everywhere, and a word wrongly badged `es-AR` is worse than one
left plain — §9.2 renders the badge as fact, next to a "MX: …" line.

That gets defended three times over, because the prompt alone will not hold:

1. the instructions state it, with worked examples of words that are *not*
   regional, which is the harder half to teach;
2. `parse_variety` returns `general` for anything unrecognised;
3. `VarietySense.normalised` strips a `homeEquivalent` from any sense that has
   no business carrying one.

## What the gloss half reuses

`render_batch`, `normalize_gloss` and `echoed_lemma` come from
`molcajete_prep`. They encode what "one to three words" means, and what the
prompt's own `·` separator does to an echoed lemma — facts about the shared
pipeline rather than about dialect. Reimplementing them here would let the two
drift on what a card holds, which is exactly what CLAUDE.md §4 is about.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from molcajete_prep.glossing.models import (
    MAX_UNITS,
    MAX_WORDS_PER_UNIT,
    Gloss,
    GlossSource,
    normalize_gloss,
)
from molcajete_prep.glossing.ollama import Rejected, echoed_lemma
from molcajete_prep.glossing.prompts import render_batch
from molcajete_prep.glossing.provider import GlossTask, Identity

from rocola_prep.variety.models import (
    Register,
    Variety,
    VarietySense,
    parse_register,
    parse_variety,
)

#: Stored on every cached row. Bump when a change here would change an answer;
#: that is how a later run tells a stale row from a fresh one without
#: re-inferring the lot.
PROMPT_VERSION = 1

_VARIETY_VALUES = [v.value for v in Variety]
_REGISTER_VALUES = [r.value for r in Register]

VARIETY_SCHEMA: dict = {
    "type": "object",
    # `glosses`, not `senses`, and not by preference. The shared provider's
    # `_parse_body` unwraps the response by that name — it is the envelope the
    # transport owns, where the objects inside it are ours. Renaming it here
    # would mean widening the upstream seam by a field to carry a word nobody
    # outside these two files ever sees.
    "properties": {
        "glosses": {
            "type": "array",
            "description": "One object per lemma given, in any order.",
            "items": {
                "type": "object",
                "properties": {
                    "lemma": {
                        "type": "string",
                        "description": "Echo the lemma exactly as given.",
                    },
                    "pos": {
                        "type": "string",
                        "description": "Echo the part-of-speech tag exactly as given.",
                    },
                    # German first, and first in the schema. §7.5: the model
                    # produces better German when it is not translating from
                    # its own English.
                    "glossDe": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "German gloss, one to three words. Null if none is possible.",
                    },
                    "glossEn": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "English gloss, one to three words. Null if none is possible.",
                    },
                    "variety": {
                        "type": "string",
                        "enum": _VARIETY_VALUES,
                        "description": "'general' unless the word is genuinely regional.",
                    },
                    "register": {
                        "type": "string",
                        "enum": _REGISTER_VALUES,
                        "description": "'neutral' unless the word is marked.",
                    },
                    "homeEquivalent": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "What a speaker of the home dialect says instead. Null if they say the same word.",
                    },
                    "homeEquivalentNote": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "One short German sentence about the difference. Null if there is none.",
                    },
                    "morphNote": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "For voseo or vosotros forms: the form, and the home-dialect equivalent. German.",
                    },
                    "notSpanish": {
                        "type": "boolean",
                        "description": "True if the string is not a real Spanish word.",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "0 to 1. How sure you are of the variety, not of the gloss.",
                    },
                },
                "required": ["lemma", "pos", "glossDe", "glossEn", "variety", "register"],
            },
        }
    },
    "required": ["glosses"],
}


def build_system_prompt(home_dialect: Variety = Variety.MX) -> str:
    """§7.5's instructions, with the reader's own Spanish named in them."""
    home = home_dialect.value
    home_name = _DIALECT_NAMES.get(home_dialect, home)

    return f"""\
You are a Spanish lexicographer preparing flashcards for a German-speaking \
learner whose home dialect is **{home} ({home_name})**. They read song lyrics \
from across the Spanish-speaking world.

You will be given a batch of lemmas, each with a part-of-speech tag and usually \
a line from the song where it appears. Answer with one object per lemma, \
echoing the lemma and tag you were given.

## The glosses

A gloss is a translation, not a definition. One to three words. If several \
translations are natural, give at most three, comma-separated, best first.

Write what a bilingual dictionary puts in bold, not what an encyclopedia puts \
in a paragraph. "lunes" is "der Montag" — not "der erste Wochentag". If you \
find yourself writing a relative clause, you are defining rather than \
translating.

Write "glossDe" first and independently. English is a disambiguator, not a \
translation of your German. For German nouns include the article — "der Junge" \
— because it carries a gender Spanish does not supply. German verbs in the \
infinitive; no "to" on English verbs.

Gloss the sense the song actually uses. The example line settles it and \
outranks whatever sense is most common in general Spanish.

## Variety — read this twice

"variety" is "{Variety.GENERAL.value}" unless the word is genuinely tied to one \
country's Spanish. **Most words are general.** "corazón", "camino", "luna", \
"querer", "noche", "bailar" are general. They are general in every song, in \
every country, and marking one regional puts a badge on a card that lies.

Mark a variety only when a speaker from elsewhere would not use the word, or \
would understand it as foreign. If you are unsure, answer \
"{Variety.GENERAL.value}". An unmarked regionalism costs the learner a footnote. \
A marked ordinary word costs them their trust in every badge you set.

Genuinely regional: "pibe" (es-AR), "chido" (es-MX), "vale" as an interjection \
(es-ES), "chévere" (es-VE), "guagua" for a bus (es-CU), "platicar" (es-MX), \
"pana" (es-PR), "polola" (es-CL).

Not regional, however Mexican the singer: "amor", "vida", "sentir", "llorar", \
"tierra", "cielo", "mujer", "sueño", "olvidar", "besar".

## The home equivalent

"homeEquivalent" is what a speaker in **{home}** would say instead.

- If "variety" is "{Variety.GENERAL.value}", "homeEquivalent" **must** be null.
- If "variety" is "{home}", "homeEquivalent" **must** be null — it is already \
their word.
- Otherwise give the word they would actually use, or null if they would use \
the same one. Never a synonym for its own sake.

"homeEquivalentNote" is one short German sentence, or null. \
Example for "pibe" with home {home}: "In Mexiko sagt man 'chavo' oder 'morro'."

## Register and morphology

"register" is "neutral" unless the word is marked: "coloquial", "vulgar", \
"poetic", "arcaic", or "albur" for Mexican double-meaning wordplay.

"morphNote" is for verb forms from voseo ("sos", "tenés", "querés", "vení") \
and vosotros ("sois", "tenéis", "venid"). Name the form and give the \
{home} equivalent, in German: "Voseo; in Mexiko 'eres'." Null otherwise.

## Words that are not words

These lemmas come from an automatic lemmatizer that invents things. When a \
string is not a real Spanish word, set "notSpanish" true and both glosses null. \
Do not guess a meaning from the word's shape — a fabricated gloss is worse than \
a missing one, because nothing downstream can tell them apart. A real but \
obscure or archaic word is not "notSpanish"; gloss it normally.

## Confidence

"confidence" is how sure you are of the **variety**, not of the gloss. Use it \
honestly; a low number on a regional guess is more useful than a confident one.

## Worked examples

Input:  corazón · NOUN · "Ay corazón, no llores más"
Output: glossDe "das Herz" · glossEn "heart" · variety general · register neutral · homeEquivalent null · confidence 0.98

Input:  pibe · NOUN · "El pibe del barrio no vuelve más"
Output: glossDe "der Junge, der Kerl" · glossEn "kid, guy" · variety es-AR · register coloquial · homeEquivalent "chavo" · homeEquivalentNote "In Mexiko sagt man 'chavo' oder 'morro'." · confidence 0.9

Input:  chido · ADJ · "Está bien chido tu carro"
Output: glossDe "cool, super" · glossEn "cool, great" · variety es-MX · register coloquial · homeEquivalent null · confidence 0.95

Input:  amor · NOUN · "Y así te vas a quedar, amor"
Output: glossDe "die Liebe" · glossEn "love" · variety general · register neutral · homeEquivalent null · confidence 0.99

Input:  sos · VERB · "Vos sos lo que yo quiero"
Output: glossDe "sein" · glossEn "to be" · variety es-AR · register neutral · morphNote "Voseo, 2. Person Singular; in Mexiko 'eres'." · confidence 0.92

Return an object for every lemma you were given, and no others.\
"""


_DIALECT_NAMES = {
    Variety.MX: "Mexico",
    Variety.AR: "Argentina",
    Variety.ES: "Spain",
    Variety.CO: "Colombia",
    Variety.CL: "Chile",
    Variety.PE: "Peru",
    Variety.VE: "Venezuela",
    Variety.PR: "Puerto Rico",
    Variety.DO: "the Dominican Republic",
    Variety.CU: "Cuba",
    Variety.UY: "Uruguay",
    Variety.EC: "Ecuador",
    Variety.GT: "Guatemala",
    Variety.BO: "Bolivia",
    Variety.PY: "Paraguay",
    Variety.CR: "Costa Rica",
    Variety.PA: "Panama",
    Variety.HN: "Honduras",
    Variety.SV: "El Salvador",
    Variety.NI: "Nicaragua",
}


_RULES_AGAIN = f"""\
Rules, again, and nothing else matters here:
- A gloss is at most {MAX_UNITS} alternatives separated by commas.
- Each alternative is at most {MAX_WORDS_PER_UNIT} words.
- "variety" is "general" unless the word is genuinely tied to one country.
- "homeEquivalent" is null whenever "variety" is "general".
- Echo the lemma and the tag exactly as they were given.
- Answer for every lemma listed, and for no others.\
"""


def render_correction(items: list[dict], *, offending: str, reason: str) -> str:
    """The retry turn. Rocola's rules, not Molcajete's.

    A correction that restates rules the model was never given is worse than no
    correction — it invites the model to answer a question about mexicanisms
    when it was asked about varieties.
    """
    quoted = offending.strip()
    if len(quoted) > 400:
        quoted = quoted[:400] + " …"
    return (
        "Your previous answer was rejected.\n\n"
        f"Problem: {reason}.\n"
        f"You wrote: {quoted}\n\n"
        f"{_RULES_AGAIN}\n\n"
        f"{render_batch(items)}"
    )


def _clean(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _checked(text: str | None, language: str, *, strict: bool) -> tuple[str | None, bool]:
    """The one-to-three-word rule, derived from `normalize_gloss` not restated.

    Same policy the shared provider uses: while a retry is available any
    shortening is a rejection, and on the last attempt a merely `trimmed` gloss
    is kept while a `clipped` one — the wreckage of a definition — is not.
    """
    if text is None:
        return None, False
    normalized = normalize_gloss(text)
    if not normalized.was_shortened:
        return normalized.text, False
    if strict or normalized.clipped:
        raise Rejected(
            f"the {language} gloss {text!r} is longer than "
            f"{MAX_UNITS} alternatives of {MAX_WORDS_PER_UNIT} words each",
            "over_length",
            raw=text,
        )
    return normalized.text, True


@dataclass
class VarietyParser:
    """`parse_item` for the shared provider, keeping the variety half.

    The provider's contract is `(Gloss, bool)` because that is what its caller
    assembles. The dialect fields have nowhere to go in a `Gloss` — and
    CLAUDE.md §4 forbids teaching the shared package about them — so they are
    collected here, keyed by the same identity the provider uses.

    Mutated from worker threads, one key each. Distinct keys into a dict is
    safe in CPython and the provider never asks two workers about one lemma.
    """

    home_dialect: Variety = Variety.MX
    senses: dict[Identity, VarietySense] = field(default_factory=dict)

    def __call__(
        self, item: Any, task: GlossTask, *, strict: bool = True
    ) -> tuple[Gloss, bool]:
        if not isinstance(item, dict):
            raise Rejected("the answer was not an object", "missing_fields")

        echoed = (echoed_lemma(item.get("lemma")), str(item.get("pos", "")).strip())
        if echoed != (task.lemma.lower(), task.pos):
            raise Rejected(
                f"the answer named {echoed[0]!r}/{echoed[1]}, "
                f"not {task.lemma!r}/{task.pos}",
                "wrong_echo",
            )

        not_spanish = bool(item.get("notSpanish", False))
        de, de_short = _checked(_clean(item.get("glossDe")), "German", strict=strict)
        en, en_short = _checked(_clean(item.get("glossEn")), "English", strict=strict)
        if not_spanish:
            de = en = None

        variety = parse_variety(item.get("variety"))
        confidence = item.get("confidence")

        sense = VarietySense(
            lemma=task.lemma,
            pos=task.pos,
            de=de,
            en=en,
            variety=variety,
            register=parse_register(item.get("register")),
            home_equivalent=_clean(item.get("homeEquivalent")),
            home_equivalent_note=_clean(item.get("homeEquivalentNote")),
            morph_note=_clean(item.get("morphNote")),
            confidence=float(confidence) if isinstance(confidence, (int, float)) else None,
        ).normalised(self.home_dialect)

        self.senses[task.identity] = sense

        # `mexicanism` is Molcajete's field and Rocola's teach rule needs the
        # broader question — SPEC §5 promotes a regional word below the
        # frequency floor, and for a pan-Hispanic rotation "regional" is the
        # useful sense of that, not "Mexican". So it carries `is_regional`.
        return (
            Gloss(
                lemma=task.lemma,
                pos=task.pos,
                de=de,
                en=en,
                de_source=GlossSource.OLLAMA if de else None,
                en_source=GlossSource.OLLAMA if en else None,
                mexicanism=sense.variety.is_regional,
                region_note=_region_note(sense),
                not_spanish=not_spanish,
            ),
            de_short or en_short,
        )


def _region_note(sense: VarietySense) -> str | None:
    """Molcajete's free-text note, rebuilt from the structured fields.

    Kept populated so that anything reading a `Gloss` — the report, a bundle
    validator — still sees a human-readable label rather than an empty field
    beside `mexicanism: true`, which `Gloss.__post_init__` treats as an
    invariant violation and silently fills with a default.
    """
    parts = [sense.variety.badge] if sense.variety.is_regional else []
    if sense.register is not Register.NEUTRAL:
        parts.append(sense.register.value)
    return ", ".join(parts) or None
