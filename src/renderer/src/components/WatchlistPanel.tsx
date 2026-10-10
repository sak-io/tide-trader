import { useEffect, useState } from 'react'
import type { WatchlistItem } from '../../../shared/types'

export default function WatchlistPanel(): JSX.Element {
  const [items, setItems] = useState<WatchlistItem[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    let cancelled = false

    window.alpaca
      .listWatchlist()
      .then((data) => {
        if (!cancelled) setItems(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load watchlist')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  async function handleAdd(event: React.FormEvent): Promise<void> {
    event.preventDefault()
    const symbol = input.trim().toUpperCase()
    if (!symbol) return

    setSubmitting(true)
    setError(null)
    try {
      const added = await window.alpaca.addToWatchlist(symbol)
      setItems((current) => {
        if (current.some((item) => item.symbol === added.symbol)) return current
        return [...current, added].sort((a, b) => a.symbol.localeCompare(b.symbol))
      })
      setInput('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add symbol')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRemove(symbol: string): Promise<void> {
    setError(null)
    try {
      await window.alpaca.removeFromWatchlist(symbol)
      setItems((current) => current.filter((item) => item.symbol !== symbol))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove symbol')
    }
  }

  return (
    <div className="watchlist-panel">
      <h2>Watchlist</h2>
      <p className="subtitle">
        Symbols here are always included in the trade-suggestion scan, alongside Alpaca&apos;s
        most-active/movers lists. Saved on the backend, so it survives restarts.
      </p>

      {error && <div className="error-banner">{error}</div>}

      <form className="watchlist-add-form" onSubmit={handleAdd}>
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Add a symbol, e.g. AAPL"
          disabled={submitting}
        />
        <button type="submit" disabled={submitting || !input.trim()}>
          Add
        </button>
      </form>

      {loading && <div className="loading-row">Loading watchlist…</div>}

      {!loading && items.length === 0 && <div className="empty-state">No symbols on your watchlist yet.</div>}

      {!loading && items.length > 0 && (
        <ul className="watchlist-list">
          {items.map((item) => (
            <li key={item.symbol} className="watchlist-row">
              <span className="symbol">{item.symbol}</span>
              <button className="link-btn" onClick={() => handleRemove(item.symbol)}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
