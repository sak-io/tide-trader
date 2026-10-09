import { useEffect, useState } from 'react'
import type { Suggestion, SuggestionOutcome, SuggestionPerformance } from '../../../shared/types'

const DOWNLOAD_RANGES: { label: string; hours: number | undefined }[] = [
  { label: '24h', hours: 24 },
  { label: '2d', hours: 48 },
  { label: '7d', hours: 168 },
  { label: 'All', hours: undefined }
]

const OUTCOME_LABELS: Record<SuggestionOutcome, string> = {
  open: 'Open',
  target_hit: 'Target hit',
  stopped: 'Stopped out',
  expired: 'Expired'
}

const REFRESH_INTERVAL_MS = 60_000

function formatPct(value: number | null): string {
  if (value === null) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

function returnClass(value: number | null): string {
  if (value === null || value === 0) return ''
  return value > 0 ? 'return-positive' : 'return-negative'
}

export default function SuggestionsPanel(): JSX.Element {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  const [performance, setPerformance] = useState<SuggestionPerformance | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)
  const [downloadMessage, setDownloadMessage] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load(): Promise<void> {
      try {
        const data = await window.alpaca.listSuggestions('pending')
        if (!cancelled) setSuggestions(data)
        try {
          const summary = await window.alpaca.getSuggestionPerformance()
          if (!cancelled) setPerformance(summary)
        } catch {
          // The summary is supplementary - never block the list on it.
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load suggestions')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    // Outcomes are resolved server-side every scan cycle; poll to pick them up.
    const refresh = setInterval(load, REFRESH_INTERVAL_MS)

    const unsubscribe = window.alpaca.onNewSuggestion((incoming) => {
      setSuggestions((current) => {
        const existingIds = new Set(current.map((s) => s.id))
        const additions = incoming.filter((s) => !existingIds.has(s.id))
        return additions.length > 0 ? [...additions, ...current] : current
      })
    })

    return () => {
      cancelled = true
      clearInterval(refresh)
      unsubscribe()
    }
  }, [])

  async function handleDismiss(id: number): Promise<void> {
    try {
      await window.alpaca.dismissSuggestion(id)
      setSuggestions((current) => current.filter((s) => s.id !== id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to dismiss suggestion')
    }
  }

  async function handleDownload(hours: number | undefined): Promise<void> {
    setDownloading(true)
    setDownloadMessage(null)
    try {
      const result = await window.alpaca.exportSuggestions(hours)
      if (result.success && result.path) {
        setDownloadMessage(`Saved to ${result.path}`)
      } else if (!result.success && result.error) {
        setDownloadMessage(result.error)
      }
      // A cancelled save dialog is neither a success nor an error - leave the
      // message blank rather than reporting a spurious failure.
    } catch (err) {
      setDownloadMessage(err instanceof Error ? err.message : 'Failed to export suggestions')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="suggestions-panel">
      <div className="suggestions-panel-header">
        <h2>Trade Suggestions</h2>
        <div className="download-toolbar">
          <span className="download-label">Download:</span>
          {DOWNLOAD_RANGES.map((range) => (
            <button
              key={range.label}
              className="link-btn"
              disabled={downloading}
              onClick={() => handleDownload(range.hours)}
            >
              {range.label}
            </button>
          ))}
        </div>
      </div>

      {performance && performance.total > 0 && (
        <div className="performance-strip" aria-label="Hypothetical performance">
          <span>{performance.total} tracked</span>
          <span>{performance.open} open</span>
          <span>{performance.targetHit} hit target</span>
          <span>{performance.stopped} stopped</span>
          <span>
            Win rate {performance.winRatePct === null ? '—' : `${performance.winRatePct.toFixed(0)}%`}
          </span>
          <span className={returnClass(performance.avgReturnPct)}>
            Avg {formatPct(performance.avgReturnPct)}
          </span>
        </div>
      )}

      {downloadMessage && <div className="loading-row">{downloadMessage}</div>}
      {error && <div className="error-banner">{error}</div>}
      {loading && !error && <div className="loading-row">Loading suggestions…</div>}

      {!loading && !error && suggestions.length === 0 && (
        <div className="empty-state">No pending suggestions right now.</div>
      )}

      {!loading && suggestions.length > 0 && (
        <ul className="suggestions-list">
          {suggestions.map((suggestion) => (
            <li key={suggestion.id} className="suggestion-row">
              <div className="suggestion-row-header">
                <span className="symbol">{suggestion.symbol}</span>
                <span className={`suggestion-direction suggestion-direction-${suggestion.direction}`}>
                  {suggestion.direction === 'bullish' ? '▲ Bullish' : '▼ Bearish'}
                </span>
                <span className="suggestion-price">${suggestion.price.toFixed(2)}</span>
                <span className="suggestion-score">Score {Math.round(suggestion.score)}</span>
              </div>

              <div className="suggestion-plan">
                <span>Stop {suggestion.stopPrice === null ? '—' : `$${suggestion.stopPrice.toFixed(2)}`}</span>
                <span>Target {suggestion.targetPrice === null ? '—' : `$${suggestion.targetPrice.toFixed(2)}`}</span>
                <span className={`outcome-badge outcome-${suggestion.outcome}`}>
                  {OUTCOME_LABELS[suggestion.outcome]}
                </span>
                <span className={returnClass(suggestion.returnPct)}>{formatPct(suggestion.returnPct)}</span>
              </div>

              <div className="suggestion-sources">
                {suggestion.sources.map((source) => (
                  <span key={source} className={`status-pill suggestion-source-${source}`}>
                    {source}
                  </span>
                ))}
              </div>

              <p className="suggestion-rationale">{suggestion.rationale ?? 'No rationale available.'}</p>

              <button className="link-btn" onClick={() => handleDismiss(suggestion.id)}>
                Dismiss
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
