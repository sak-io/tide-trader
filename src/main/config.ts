import { app, safeStorage } from 'electron'
import { readFileSync, writeFileSync, existsSync, mkdirSync, unlinkSync } from 'node:fs'
import { join } from 'node:path'
import type { Credentials } from '../shared/types'

interface StoredConfig {
  keyId: string
  encryptedSecret: string
  encrypted: boolean
}

export type { Credentials }

function configPath(): string {
  const dir = app.getPath('userData')
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
  return join(dir, 'alpaca-config.json')
}

export function loadCredentials(): Credentials | null {
  const path = configPath()
  if (!existsSync(path)) return null

  const raw = JSON.parse(readFileSync(path, 'utf-8')) as StoredConfig
  const secret = raw.encrypted
    ? safeStorage.decryptString(Buffer.from(raw.encryptedSecret, 'base64'))
    : raw.encryptedSecret

  return { keyId: raw.keyId, secret }
}

export function saveCredentials(credentials: Credentials): void {
  const canEncrypt = safeStorage.isEncryptionAvailable()
  const stored: StoredConfig = {
    keyId: credentials.keyId,
    encryptedSecret: canEncrypt
      ? safeStorage.encryptString(credentials.secret).toString('base64')
      : credentials.secret,
    encrypted: canEncrypt
  }

  writeFileSync(configPath(), JSON.stringify(stored), 'utf-8')
}

export function clearCredentials(): void {
  const path = configPath()
  if (existsSync(path)) unlinkSync(path)
}
