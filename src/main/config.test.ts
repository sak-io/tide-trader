import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

let userDataDir: string
let encryptionAvailable = true

vi.mock('electron', () => ({
  app: {
    getPath: () => userDataDir
  },
  safeStorage: {
    isEncryptionAvailable: () => encryptionAvailable,
    encryptString: (value: string) => Buffer.from(`enc:${value}`, 'utf-8'),
    decryptString: (buffer: Buffer) => buffer.toString('utf-8').replace(/^enc:/, '')
  }
}))

import { clearCredentials, loadCredentials, saveCredentials } from './config'

describe('credential storage', () => {
  beforeEach(() => {
    userDataDir = mkdtempSync(join(tmpdir(), 'tide-trader-test-'))
    encryptionAvailable = true
  })

  afterEach(() => {
    rmSync(userDataDir, { recursive: true, force: true })
  })

  it('returns null when nothing has been saved yet', () => {
    expect(loadCredentials()).toBeNull()
  })

  it('round-trips credentials through encrypted storage', () => {
    saveCredentials({ keyId: 'PKTEST', secret: 'shh' })
    expect(loadCredentials()).toEqual({ keyId: 'PKTEST', secret: 'shh' })
  })

  it('falls back to plaintext storage when OS encryption is unavailable', () => {
    encryptionAvailable = false
    saveCredentials({ keyId: 'PKTEST', secret: 'shh' })
    expect(loadCredentials()).toEqual({ keyId: 'PKTEST', secret: 'shh' })
  })

  it('clearCredentials deletes the file so loadCredentials returns null again', () => {
    saveCredentials({ keyId: 'PKTEST', secret: 'shh' })
    expect(loadCredentials()).not.toBeNull()

    clearCredentials()

    // Regression test: clearCredentials used to overwrite the file with `{}`
    // instead of deleting it, which loadCredentials would then happily parse
    // as a truthy-but-empty set of credentials.
    expect(loadCredentials()).toBeNull()
  })

  it('clearCredentials is a no-op when nothing was ever saved', () => {
    expect(() => clearCredentials()).not.toThrow()
  })
})
