export interface Credentials {
  keyId: string
  secret: string
}

export interface AssetSummary {
  symbol: string
  name: string
  exchange: string
  tradable: boolean
}

export interface TradeUpdate {
  symbol: string
  price: number
  size: number
  timestamp: string
}

export interface QuoteUpdate {
  symbol: string
  bidPrice: number
  bidSize: number
  askPrice: number
  askSize: number
  timestamp: string
}

export interface BarUpdate {
  symbol: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  timestamp: string
}

export type StreamStatus =
  | 'disconnected'
  | 'connecting'
  | 'connected'
  | 'auth_failed'
  | 'error'

export interface AlpacaStatus {
  connected: boolean
}

export interface SaveCredentialsResult {
  success: boolean
  error?: string
}

export interface ExportSuggestionsResult {
  success: boolean
  path?: string
  error?: string
}

export interface LatestSnapshot {
  trade?: TradeUpdate
  quote?: QuoteUpdate
  bar?: BarUpdate
}

export interface ActiveTicker {
  symbol: string
  volume: number
  tradeCount: number
}

export interface MoverTicker {
  symbol: string
  percentChange: number
  change: number
  price: number
}

export interface MarketMovers {
  gainers: MoverTicker[]
  losers: MoverTicker[]
}

export interface HistoricalBar {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export type BarTimeframe = '1Min' | '5Min' | '15Min' | '1Hour' | '1Day'

export type SignalSource = 'alpaca' | 'watchlist'

export type SignalDirection = 'bullish' | 'bearish'

export type SuggestionStatus = 'pending' | 'dismissed'

export interface SuggestionIndicators {
  smaFast: number
  smaSlow: number
  rsi14: number
  volumeRatio: number
}

export interface WatchlistItem {
  symbol: string
  addedAt: string
}

export interface Suggestion {
  id: number
  symbol: string
  direction: SignalDirection
  price: number
  score: number
  indicators: SuggestionIndicators
  triggeredRules: string[]
  sources: SignalSource[]
  rationale: string | null
  status: SuggestionStatus
  generatedAt: string
  updatedAt: string
}
