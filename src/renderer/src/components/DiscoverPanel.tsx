import { useEffect, useState } from 'react'
import type { ActiveTicker, MoverTicker } from '../../../shared/types'

type Tab = 'active' | 'gainers' | 'losers'

interface Row {
  symbol: string
  primary: string
  secondary: string
  tone?: 'up' | 'down'
}

interface Props {
  selectedSymbol: string | null
  onSelect: (symbol: string) => void
}

export default function DiscoverPanel({ selectedSymbol, onSelect }: Props): JSX.Element {
  const [tab, setTab] = useState<Tab>('active')
  const [activeTickers, setActiveTickers] = useState<ActiveTicker[]>([])
  const [gainers, setGainers] = useState<MoverTicker[]>([])
  const [losers, setLosers] = useState<MoverTicker[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    async function load(): Promise<void> {
      try {
        if (tab === 'active') {
          const data = await window.alpaca.getMostActive(15)
          if (!cancelled) setActiveTickers(data)
        } else {
          const data = await window.alpaca.getMovers(15)
          if (!cancelled) {
            setGainers(data.gainers)
            setLosers(data.losers)
          }
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load market data')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [tab])

  const rows: Row[] =
    tab === 'active'
      ? activeTickers.map((ticker) => ({
          symbol: ticker.symbol,
          primary: `${(ticker.volume / 1_000_000).toFixed(1)}M vol`,
          secondary: `${Math.round(ticker.tradeCount).toLocaleString()} trades`
        }))
      : (tab === 'gainers' ? gainers : losers).map((mover) => ({
          symbol: mover.symbol,
          primary: `$${mover.price.toFixed(2)}`,
          secondary: `${mover.percentChange >= 0 ? '▲' : '▼'} ${Math.abs(mover.percentChange).toFixed(2)}%`,
          tone: mover.percentChange >= 0 ? 'up' : 'down'
        }))

  return (
    <div className="discover-panel">
      <div className="discover-tabs">
        <button className={tab === 'active' ? 'tab-active' : ''} onClick={() => setTab('active')}>
          Most Active
        </button>
        <button className={tab === 'gainers' ? 'tab-active' : ''} onClick={() => setTab('gainers')}>
          Gainers
        </button>
        <button className={tab === 'losers' ? 'tab-active' : ''} onClick={() => setTab('losers')}>
          Losers
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}
      {loading && !error && <div className="loading-row">Loading…</div>}

      {!loading && !error && (
        <ul className="discover-list">
          {rows.map((row) => (
            <li
              key={row.symbol}
              className={row.symbol === selectedSymbol ? 'selected' : ''}
              onClick={() => onSelect(row.symbol)}
            >
              <span className="symbol">{row.symbol}</span>
              <span className="primary">{row.primary}</span>
              <span className={`secondary ${row.tone ?? ''}`}>{row.secondary}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
