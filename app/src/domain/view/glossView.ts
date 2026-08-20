/**
 * View model for the tap-to-gloss sheet.
 *
 * The interesting case is the missing German gloss. Wiktionary does not reach
 * SPEC §12's 95% on its own, the model half rejects lemmas it does not believe
 * are Spanish, and a Phase 1 bundle has no glosses at all — so "no gloss" is a
 * normal state, not a bug, and the sheet has to say so rather than opening
 * blank and looking broken.
 */

import { badgeFor, type LemmaKey, type LexiconEntry, type Register, type Variety } from '../types'

export interface GlossView {
  key: LemmaKey
  lemma: string
  pos: string
  /** null when the pipeline produced no German gloss for this lemma. */
  de: string | null
  en: string | null
  /** The sentence from this book that the gloss was disambiguated against. */
  example: string | null
  variety: Variety
  register: Register
  /**
   * SPEC §9.2's badge, or null when there is none to show.
   *
   * The reader's own surface gets this too, not only the card back: someone
   * tapping `pibe` mid-song wants to know it is Argentine right then, which is
   * the moment the information is worth anything.
   */
  badge: string | null
  /** What a speaker at home would say instead. Null when they say the same. */
  homeEquivalent: string | null
  /** §9.3: voseo and vosotros. Recognisable, never drilled. */
  morphNote: string | null
}

export function buildGlossView(
  key: LemmaKey,
  entry: LexiconEntry | undefined,
  homeDialect: Variety,
): GlossView | null {
  if (!entry) return null
  return {
    key,
    lemma: entry.lemma,
    pos: entry.pos,
    de: entry.de ?? null,
    en: entry.en ?? null,
    example: entry.example?.es ?? null,
    variety: entry.variety,
    register: entry.register,
    badge: badgeFor(entry.variety, homeDialect),
    homeEquivalent: entry.homeEquivalent ?? null,
    morphNote: entry.morphNote ?? null,
  }
}
