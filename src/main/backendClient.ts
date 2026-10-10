import { readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import type {
  ActiveTicker,
  AlpacaStatus,
  BarTimeframe,
  Credentials,
  HistoricalBar,
  MarketMovers,
  MoverTicker,
  SaveCredentialsResult,
  Suggestion,
  SuggestionIndicators,
  SuggestionOutcome,
  SuggestionPerformance,
  SuggestionStatus,
  WatchlistItem
} from '../shared/types'

const BACKEND_BASE_URL = 'http://127.0.0.1:8000'

// The backend generates this on first run and writes it here (owner-only) - see
// core/app/security/access_token.py. Both processes read/write this same
// well-known path, so there's no login/hand-off endpoint needed between them.
// homedir() and Python's Path.home() agree on every platform (on Windows both
// resolve %USERPROFILE%), so this is %USERPROFILE%\.tide-trader\access-token there.
const ACCESS_TOKEN_PATH = join(homedir(), '.tide-trader', 'access-token')

function readAccessToken(): string {
  try {
    return readFileSync(ACCESS_TOKEN_PATH, 'utf-8').trim()
  } catch {
    throw new Error(
      `Could not read the Tide Trader backend's access token at ${ACCESS_TOKEN_PATH}. ` +
        'Is the backend running yet? (run `uv run python -m app.main` in the core/ directory)'
    )
  }
}

async function backendRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  // Thrown directly (not folded into the network try/catch below) so its specific,
  // actionable message reaches the caller instead of the generic "could not reach
  // the backend" one.
  const token = readAccessToken()

  let response: Response
  try {
    response = await fetch(`${BACKEND_BASE_URL}${path}`, {
      ...init,
      headers: { ...init.headers, Authorization: `Bearer ${token}` }
    })
  } catch {
    throw new Error(
      `Could not reach the Tide Trader backend at ${BACKEND_BASE_URL}. ` +
        'Is it running? (run `uv run python -m app.main` in the core/ directory)'
    )
  }

  if (!response.ok) {
    throw new Error(await describeErrorResponse(response))
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function describeErrorResponse(response: Response): Promise<string> {
  const body = await response.text().catch(() => '')
  try {
    const parsed = JSON.parse(body) as { detail?: unknown }
    if (typeof parsed.detail === 'string') return parsed.detail
  } catch {
    // Not JSON - fall through to the raw body below.
  }
  return `Backend request failed: HTTP ${response.status}${body ? ` - ${body}` : ''}`
}

function jsonRequest(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
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
  const raw = await backendRequest<RawActiveTicker[]>(`/api/v1/market/most-active?top=${top}`)
  return raw.map((item) => ({ symbol: item.symbol, volume: item.volume, tradeCount: item.trade_count }))
}

export async function fetchMovers(top = 10): Promise<MarketMovers> {
  const raw = await backendRequest<{ gainers: RawMoverTicker[]; losers: RawMoverTicker[] }>(
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
  return backendRequest<HistoricalBar[]>(`/api/v1/market/bars/${encodeURIComponent(symbol)}?${query.toString()}`)
}

export async function connectAlpaca(credentials: Credentials): Promise<SaveCredentialsResult> {
  try {
    await backendRequest<AlpacaStatus>(
      '/api/v1/alpaca/connect',
      jsonRequest('POST', { api_key_id: credentials.keyId, secret_key: credentials.secret })
    )
    return { success: true }
  } catch (err) {
    return { success: false, error: err instanceof Error ? err.message : 'Unknown error' }
  }
}

export async function getAlpacaStatus(): Promise<AlpacaStatus> {
  return backendRequest<AlpacaStatus>('/api/v1/alpaca/status')
}

export async function disconnectAlpaca(): Promise<void> {
  await backendRequest<void>('/api/v1/alpaca/disconnect', { method: 'DELETE' })
}

interface RawSuggestionIndicators {
  sma_fast: number
  sma_slow: number
  rsi14: number
  volume_ratio: number
}

interface RawSuggestion {
  id: number
  symbol: string
  direction: Suggestion['direction']
  price: number
  score: number
  stop_price: number | null
  target_price: number | null
  outcome: SuggestionOutcome
  outcome_price: number | null
  outcome_at: string | null
  last_price: number | null
  return_pct: number | null
  indicators: RawSuggestionIndicators
  triggered_rules: string[]
  sources: Suggestion['sources']
  rationale: string | null
  status: SuggestionStatus
  generated_at: string
  updated_at: string
}

function toSuggestionIndicators(raw: RawSuggestionIndicators): SuggestionIndicators {
  return {
    smaFast: raw.sma_fast,
    smaSlow: raw.sma_slow,
    rsi14: raw.rsi14,
    volumeRatio: raw.volume_ratio
  }
}

function toSuggestion(raw: RawSuggestion): Suggestion {
  return {
    id: raw.id,
    symbol: raw.symbol,
    direction: raw.direction,
    price: raw.price,
    score: raw.score,
    stopPrice: raw.stop_price,
    targetPrice: raw.target_price,
    outcome: raw.outcome,
    outcomePrice: raw.outcome_price,
    outcomeAt: raw.outcome_at,
    lastPrice: raw.last_price,
    returnPct: raw.return_pct,
    indicators: toSuggestionIndicators(raw.indicators),
    triggeredRules: raw.triggered_rules,
    sources: raw.sources,
    rationale: raw.rationale,
    status: raw.status,
    generatedAt: raw.generated_at,
    updatedAt: raw.updated_at
  }
}

export async function fetchSuggestions(status: SuggestionStatus | 'all' = 'pending'): Promise<Suggestion[]> {
  const raw = await backendRequest<RawSuggestion[]>(`/api/v1/suggestions?status=${status}`)
  return raw.map(toSuggestion)
}

interface RawSuggestionPerformance {
  total: number
  open: number
  target_hit: number
  stopped: number
  expired: number
  win_rate_pct: number | null
  avg_return_pct: number | null
}

export async function fetchSuggestionPerformance(): Promise<SuggestionPerformance> {
  const raw = await backendRequest<RawSuggestionPerformance>('/api/v1/suggestions/performance')
  return {
    total: raw.total,
    open: raw.open,
    targetHit: raw.target_hit,
    stopped: raw.stopped,
    expired: raw.expired,
    winRatePct: raw.win_rate_pct,
    avgReturnPct: raw.avg_return_pct
  }
}

export async function dismissSuggestion(id: number): Promise<Suggestion> {
  const raw = await backendRequest<RawSuggestion>(`/api/v1/suggestions/${id}/dismiss`, { method: 'POST' })
  return toSuggestion(raw)
}

// Not JSON, so this bypasses `backendRequest` (which always parses the body as JSON) -
// duplicates its token-read/error-handling shape rather than generalizing backendRequest
// for one non-JSON caller.
export async function exportSuggestionsCsv(hours?: number): Promise<string> {
  const token = readAccessToken()
  const query = hours !== undefined ? `?hours=${hours}` : ''

  let response: Response
  try {
    response = await fetch(`${BACKEND_BASE_URL}/api/v1/suggestions/export${query}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
  } catch {
    throw new Error(
      `Could not reach the Tide Trader backend at ${BACKEND_BASE_URL}. ` +
        'Is it running? (run `uv run python -m app.main` in the core/ directory)'
    )
  }

  if (!response.ok) {
    throw new Error(await describeErrorResponse(response))
  }

  return response.text()
}

interface RawWatchlistItem {
  symbol: string
  added_at: string
}

function toWatchlistItem(raw: RawWatchlistItem): WatchlistItem {
  return { symbol: raw.symbol, addedAt: raw.added_at }
}

export async function fetchWatchlist(): Promise<WatchlistItem[]> {
  const raw = await backendRequest<RawWatchlistItem[]>('/api/v1/watchlist')
  return raw.map(toWatchlistItem)
}

export async function addToWatchlist(symbol: string): Promise<WatchlistItem> {
  const raw = await backendRequest<RawWatchlistItem>('/api/v1/watchlist', jsonRequest('POST', { symbol }))
  return toWatchlistItem(raw)
}

export async function removeFromWatchlist(symbol: string): Promise<void> {
  await backendRequest<void>(`/api/v1/watchlist/${encodeURIComponent(symbol)}`, { method: 'DELETE' })
}
