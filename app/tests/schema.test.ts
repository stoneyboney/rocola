/**
 * The version chain, pinned.
 *
 * ## The bug this exists to prevent, which already happened once
 *
 * Version 1 shipped with `sessions: '[bookId+chapterIndex], bookId'`. When a
 * session lost its second axis — §11.1: one song is one session, and a song is
 * never split — the version-1 declaration was *edited in place* to
 * `sessions: 'trackId'`. Same version number, different primary key.
 *
 * Every browser already holding the old database then answered:
 *
 *     UpgradeError: Not yet support for changing primary key
 *
 * and could not import anything, because opening the database is the first
 * thing an import does. IndexedDB cannot re-key a store; the only way is to
 * drop it and create a new one, in separate versions, because a store cannot be
 * both `null` and declared in one `stores()` call.
 *
 * A schema's version chain is not source code to be tidied. It is a description
 * of databases that exist on devices, and editing a shipped version is a claim
 * about them that is not true. These tests are here because reading that
 * sentence in a comment was not enough — the comment saying it was written
 * *after* the edit that broke it.
 *
 * Dexie records the whole chain without opening anything, so this runs in the
 * same plain-node environment as everything else.
 */

import { describe, expect, it } from 'vitest'

import { RocolaDatabase } from '../src/infra/db'

interface VersionCfg {
  _cfg: { version: number; storesSource: Record<string, string | null> }
}

function chain(): VersionCfg[] {
  const db = new RocolaDatabase('schema-probe') as unknown as {
    _versions: VersionCfg[]
  }
  return [...db._versions].sort((a, b) => a._cfg.version - b._cfg.version)
}

describe('version 1, as it shipped', () => {
  it('is exactly what the first release created', () => {
    // Frozen. If this test fails, the fix is a new version — never an edit
    // here, whatever the new shape is meant to be.
    const [v1] = chain()
    expect(v1!._cfg.version).toBe(1)
    expect(v1!._cfg.storesSource).toEqual({
      sessions: '[bookId+chapterIndex], bookId',
      cards: 'lemmaId, card.fsrs.due',
      knownLemmas: 'lemmaId',
    })
  })

  it('still keys sessions by book and chapter, wrong as that now is', () => {
    // It describes a world with chapters in it. That world is gone, and the
    // record of it is not.
    const [v1] = chain()
    expect(v1!._cfg.storesSource.sessions).toContain('bookId')
  })
})

describe('the re-key, split across two versions', () => {
  it('drops the session store in version 2 and nothing else', () => {
    const [, v2] = chain()
    expect(v2!._cfg.version).toBe(2)
    expect(v2!._cfg.storesSource).toEqual({ sessions: null })
  })

  it('recreates it in version 3 with the track key', () => {
    const [, , v3] = chain()
    expect(v3!._cfg.version).toBe(3)
    expect(v3!._cfg.storesSource.sessions).toBe('trackId')
  })

  it('never drops and declares one store in the same version', () => {
    // The rule the split exists to satisfy. IndexedDB cannot do both at once,
    // and Dexie will not pretend otherwise.
    for (const version of chain()) {
      const stores = version._cfg.storesSource
      const dropped = Object.keys(stores).filter((k) => stores[k] === null)
      const declared = Object.keys(stores).filter((k) => stores[k] !== null)
      expect(dropped.filter((k) => declared.includes(k))).toEqual([])
    }
  })
})

describe('the stores a song needs', () => {
  it('all arrive in version 3', () => {
    const [, , v3] = chain()
    expect(Object.keys(v3!._cfg.storesSource).sort()).toEqual([
      'lexicon',
      'positions',
      'sessions',
      'stanzas',
      'trackVocab',
      'tracks',
    ])
  })

  it('put the track id in every compound key', () => {
    // So that removing a song is a range delete, and so that there is no way
    // to read one song's stanzas beside another song's lexicon.
    const [, , v3] = chain()
    const stores = v3!._cfg.storesSource
    expect(stores.stanzas).toBe('[trackId+index], trackId')
    expect(stores.lexicon).toBe('[trackId+key], trackId')
  })
})

describe('the stores a card lives in are never re-declared', () => {
  it('cards and knownLemmas appear only in version 1', () => {
    // They hold the only data in this database that cannot be rebuilt from a
    // file on the desktop. Touching their schema risks the one thing the app
    // cannot replace, and there has never been a reason to.
    const later = chain().slice(1)
    for (const version of later) {
      expect(Object.keys(version._cfg.storesSource)).not.toContain('cards')
      expect(Object.keys(version._cfg.storesSource)).not.toContain('knownLemmas')
    }
  })
})
