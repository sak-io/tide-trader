import { afterEach, describe, expect, it, vi } from 'vitest'

const readFileSync = vi.fn()
const writeFileSync = vi.fn()
const existsSync = vi.fn()
const mkdirSync = vi.fn()
const unlinkSync = vi.fn()

// alpacaCredentialCache must never touch the filesystem - the Alpaca secret is
// in-memory only for the lifetime of this process. Mocking node:fs with spies (rather
// than just not mocking it) means any accidental fs usage is caught even if it would
// otherwise silently succeed against the real filesystem.
vi.mock('node:fs', () => ({ readFileSync, writeFileSync, existsSync, mkdirSync, unlinkSync }))

import { clear, get, set } from './alpacaCredentialCache'

afterEach(() => {
  clear()
  vi.clearAllMocks()
})

describe('alpacaCredentialCache', () => {
  it('returns null when nothing has been cached yet', () => {
    expect(get()).toBeNull()
  })

  it('round-trips credentials through the in-memory cache', () => {
    set({ keyId: 'PKTEST', secret: 'shh' })
    expect(get()).toEqual({ keyId: 'PKTEST', secret: 'shh' })
  })

  it('clear() resets the cache to null', () => {
    set({ keyId: 'PKTEST', secret: 'shh' })

    clear()

    expect(get()).toBeNull()
  })

  it('makes zero node:fs calls', () => {
    set({ keyId: 'PKTEST', secret: 'shh' })
    get()
    clear()

    expect(readFileSync).not.toHaveBeenCalled()
    expect(writeFileSync).not.toHaveBeenCalled()
    expect(existsSync).not.toHaveBeenCalled()
    expect(mkdirSync).not.toHaveBeenCalled()
    expect(unlinkSync).not.toHaveBeenCalled()
  })
})
