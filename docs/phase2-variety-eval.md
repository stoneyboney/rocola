# Variety tagging — the over-tagging eval

**Run 2026-08-20 against `gemma3:12b`. Home dialect `es-MX`. 146 lemmas.**

SPEC §15 q2 set this up as a gate:

> **Ollama over-tagging.** Expect the model to mark pan-Hispanic words as
> regional. Needs a held-out eval set of ~100 known-general lemmas to measure
> the false-positive rate before trusting `variety` in production.

## The answer inverts the question

| set | n | answered | tagged regional | |
|---|---:|---:|---:|---|
| **A** — commonest open-class lemmas, expect `general` | 100 | 100 | 0 | **0% false positives** |
| **B** — known regionalisms, expect not-`general` | 46 | 46 | 26 | **57% recall** |

**Over-tagging is not the failure mode. Under-tagging is.**

Not one of the hundred commonest Spanish words was marked regional, and not one
general sense came back carrying a `homeEquivalent` it should not have. The
thing §15 feared does not happen at this prompt.

What does happen is that twenty real regionalisms were called `general` —
including `ahorita`, `chela`, `compa`, `botana`, `apapachar`, `chambear`,
`tío`, `guay`, `boludo`, `laburo`, `quilombo`. These are not obscure.

**When it does tag, it is accurate.** Of the 26 it caught, **23 were placed in
the country the gold list names** — across eight varieties, not just Mexico.

## Why this is the tolerable direction, and where the bias came from

The prompt says so explicitly, and CLAUDE.md §5 says it first:

> An unmarked regionalism costs the learner a footnote. A marked ordinary word
> costs them their trust in every badge you set.

A badge that appears is worth believing: 0% false positives and 88% correct
placement. A badge that does not appear means nothing either way.

The bias is almost certainly *mine* rather than the model's. The prompt spends
as many words on words that are **not** regional as on ones that are, and ends
its variety section with "if you are unsure, answer general". That instruction
did exactly what it was written to do, and it did slightly too much of it.

So the honest reading: **0% false positives is not a free result, it was bought
with recall**, and the eval now exists to price the trade the other way.

## What a real song looks like

| | cards | regional | non-neutral register |
|---|---:|---:|---:|
| Selena — *Como La Flor* | 26 | 0 | — |
| Molotov — *Gimme Tha Power* | 74 | 0 | 13 (7 coloquial, 6 vulgar) |

Zero regional on both, and on *Como La Flor* that is simply correct: `amor`,
`flor`, `corazón`, `perder` are pan-Hispanic, and a badge on any of them would
be the failure §9.2 warns about.

Two things this shows that the eval could not:

**The register axis works where variety does not.** 13 of Molotov's 74 cards
carry `coloquial` or `vulgar` — `pendejo` among them, correctly `general` and
correctly `vulgar`, since it is vulgar across Latin America rather than Mexican.

**A Mexican reader listening to Mexican music should expect few badges**, and
that is by design rather than a shortfall. §9.2 gives no badge to the reader's
own dialect. The badge exists for the Argentine and Caribbean vocabulary a
pan-Hispanic rotation pulls in.

## The home dialect is genuinely a parameter

The sharpest check, same five words, two homes:

| lemma | home `es-MX` | home `es-AR` |
|---|---|---|
| chido | `es-MX`, no badge | `es-MX`, **badge MX** |
| platicar | `es-MX`, no badge | `es-MX`, **badge MX** |
| güey | `es-MX`, no badge | `es-MX`, **badge MX** |

Nothing is hard-coded, and §9.2's rule — no badge for `general`, none for the
reader's own dialect — holds end to end.

One wrinkle worth recording: `padre` in its Mexican "great" sense came back
`es-MX` when home was Mexico and `general` when home was Argentina. Whether a
word *is* Mexican should not depend on who is asking. Temperature is zero, so
this is the changed prompt rather than sampling noise — naming a different home
dialect moves the answer. It is a small instability, and it argues for treating
a single variety judgement as a hint rather than a fact.

## The gate

**`variety` is written by default.** The condition was a low false-positive
rate, and it is zero. `--no-variety` skips the pass for a faster build.

## Open, and now measurable

1. **Recall is the number to improve**, and the obvious lever is the "if unsure,
   answer general" instruction. The eval exists to check whether softening it
   buys recall without spending the 0%.
2. **`homeEquivalent` is rarely populated** even when the variety is foreign —
   `chido` with home `es-AR` produced no Argentine equivalent. §9.2's "MX: …"
   line will often be absent.
3. **Cross-run instability on the home dialect**, as above.
4. The lemmatizer still invents words and the model still glosses them —
   `viera`, a subjunctive of `ver`, came back as "der Blick". Inherited from
   Molcajete's Phase 2 and unrelated to variety.

## Method

- No cache during the eval: a warm one would measure the previous run.
- Set A is the commonest open-class lemmas from `wordfreq`, POS-tagged with
  spaCy so the closed-class words that dominate the top of that list are
  dropped. Frequency at that level is pan-Hispanic almost by definition.
- Set B is `molcajete_prep`'s shipped 26-entry mexicanism gold list plus 20
  hand-written regionalisms from Argentina, Spain, Venezuela, Cuba, Puerto
  Rico, Chile, Colombia and Peru, so recall is not measured on one country.
- One model pass: §7.5's answer carries `glossDe` and `glossEn` alongside the
  dialect fields, so glossing and tagging are the same question.
