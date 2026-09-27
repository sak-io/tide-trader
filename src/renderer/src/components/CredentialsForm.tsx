import { FormEvent, useState } from 'react'

interface Props {
  onSaved: (keyId: string) => void
}

export default function CredentialsForm({ onSaved }: Props): JSX.Element {
  const [keyId, setKeyId] = useState('')
  const [secret, setSecret] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent): Promise<void> {
    e.preventDefault()
    setSubmitting(true)
    setError(null)

    const result = await window.alpaca.saveCredentials({ keyId: keyId.trim(), secret: secret.trim() })

    setSubmitting(false)
    if (result.success) {
      onSaved(keyId.trim())
    } else {
      setError(result.error ?? 'Could not verify these keys with Alpaca.')
    }
  }

  return (
    <div className="credentials-screen">
      <form className="credentials-card" onSubmit={handleSubmit}>
        <h1>Connect your Alpaca Paper account</h1>
        <p className="subtitle">
          Generate a Paper Trading API key from your Alpaca dashboard, then paste it here. Keys
          are stored encrypted, locally on this Mac, and are only ever sent to Alpaca.
        </p>

        <label>
          API Key ID
          <input
            value={keyId}
            onChange={(e) => setKeyId(e.target.value)}
            placeholder="PK..."
            autoFocus
            required
          />
        </label>

        <label>
          Secret Key
          <input
            type="password"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder="Secret key"
            required
          />
        </label>

        {error && <div className="error-banner">{error}</div>}

        <button type="submit" disabled={submitting}>
          {submitting ? 'Verifying…' : 'Connect'}
        </button>
      </form>
    </div>
  )
}
