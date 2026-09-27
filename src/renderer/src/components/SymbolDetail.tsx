import { useEffect, useState } from 'react'
import PriceChart from './PriceChart'
import type { BarTimeframe, HistoricalBar, QuoteUpdate, TradeUpdate } from '../../../shared/types'

interface Props {
  symbol: string
}

interface RangeOption {
  label: string
  timeframe: BarTimeframe
  limit: number
}

const RANGES: RangeOption[] = [
  { label: '1D', timeframe: '5Min', limit: 78 },
  { label: '1W', timeframe: '15Min', limit: 130 },
  { label: '1M', timeframe: '1Day', limit: 30 },
  { label: '3M', timeframe: '1Day', limit: 90 },
  { label: '1Y', timeframe: '1Day', limit: 260 }
]

export default function SymbolDetail({ symbol }: Props): JSX.Element {
  const [range, setRange] = useState<RangeOption>(RANGES[2])
  const [bars, setBars] = useState<HistoricalBar[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [trade, setTrade] = useState<TradeUpdate | null>(null)
  const [quote, setQuote] = useState<QuoteUpdate | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    window.alpaca
      .getBars(symbol, range.timeframe, range.limit)
      .then((data) => {
        if (!cancelled) setBars(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load chart data')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [symbol, range])

  useEffect(() => {
    setTrade(null)
    setQuote(null)

    window.alpaca.subscribe(symbol)
    window.alpaca.getLatest(symbol).then((snapshot) => {
      if (snapshot.trade) setTrade(snapshot.trade)
      if (snapshot.quote) setQuote(snapshot.quote)
    })

    const unsubTrade = window.alpaca.onTrade((update) => {
      if (update.symbol === symbol) setTrade(update)
    })
    const unsubQuote = window.alpaca.onQuote((update) => {
      if (update.symbol === symbol) setQuote(update)
    })

    return () => {
      unsubTrade()
      unsubQuote()
      window.alpaca.unsubscribe(symbol)
    }
  }, [symbol])

  return (
    <div className="symbol-detail">
      <div className="symbol-detail-header">
        <div>
          <div className="symbol-detail-symbol">{symbol}</div>
          {quote && (
            <div className="symbol-detail-quote">
              Bid ${quote.bidPrice.toFixed(2)} · Ask ${quote.askPrice.toFixed(2)}
            </div>
          )}
        </div>
        {trade && <div className="symbol-detail-live-price">${trade.price.toFixed(2)}</div>}
      </div>

      <div className="range-selector">
        {RANGES.map((option) => (
          <button
            key={option.label}
            className={option.label === range.label ? 'range-active' : ''}
            onClick={() => setRange(option)}
          >
            {option.label}
          </button>
        ))}
      </div>

      {error && <div className="error-banner">{error}</div>}
      {loading && <div className="loading-row">Loading chart…</div>}
      {!loading && !error && <PriceChart bars={bars} />}
    </div>
  )
}
