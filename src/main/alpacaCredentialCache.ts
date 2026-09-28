import type { Credentials } from '../shared/types'

export type { Credentials }

// In-memory only, for the lifetime of this Electron process - never written to disk,
// a keyring, or anywhere else persistent. Cleared on Electron restart, same as the
// Python backend's own in-memory AlpacaConnection (see core/app/security/alpaca_session.py).
// This cache exists purely so the direct-to-Alpaca realtime streaming path
// (alpacaStream.ts) can reuse the same raw secret the user just typed into
// CredentialsForm, without prompting for it twice.
let cached: Credentials | null = null

export function get(): Credentials | null {
  return cached
}

export function set(credentials: Credentials): void {
  cached = credentials
}

export function clear(): void {
  cached = null
}
