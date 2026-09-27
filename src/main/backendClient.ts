import type { ActiveTicker, BarTimeframe, HistoricalBar, MarketMovers, MoverTicker } from '../shared/types'

const BACKEND_BASE_URL = 'http://127.0.0.1:8000'

async function backendGet<T>(path: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BACKEND_BASE_URL}${path}`)
  } catch {
    throw new Error(
      `Could not reach the Tide Trader backend at ${BACKEND_BASE_URL}. ` +
        'Is it running? (cd core && uv run python -m app.main)'
    )
  }

  if (!response.ok) {
    const body = await response.text().catch(() => '')
    throw new Error(`Backend request failed: HTTP ${response.status}${body ? ` - ${body}` : ''}`)
  }

  return response.json() as Promise<T>
}

interface RawActiveTicker {
  symbol: string
  volume: number
  trade_count: number
}

interface RawMoverTicker {
  symbol: string
  percent_change: number
  change: number
  price: number
}

function toMoverTicker(raw: RawMoverTicker): MoverTicker {
  return { symbol: raw.symbol, percentChange: raw.percent_change, change: raw.change, price: raw.price }
}

export async function fetchMostActive(top = 10): Promise<ActiveTicker[]> {
  const raw = await backendGet<RawActiveTicker[]>(`/api/v1/market/most-active?top=${top}`)
  return raw.map((item) => ({ symbol: item.symbol, volume: item.volume, tradeCount: item.trade_count }))
}

export async function fetchMovers(top = 10): Promise<MarketMovers> {
  const raw = await backendGet<{ gainers: RawMoverTicker[]; losers: RawMoverTicker[] }>(
    `/api/v1/market/movers?top=${top}`
  )
  return { gainers: raw.gainers.map(toMoverTicker), losers: raw.losers.map(toMoverTicker) }
}

export async function fetchBars(
  symbol: string,
  timeframe: BarTimeframe = '1Day',
  limit = 200
): Promise<HistoricalBar[]> {
  const query = new URLSearchParams({ timeframe, limit: String(limit) })
  return backendGet<HistoricalBar[]>(`/api/v1/market/bars/${encodeURIComponent(symbol)}?${query.toString()}`)
}
