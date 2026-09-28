import type { AssetSummary, Credentials, LatestSnapshot } from '../shared/types'

const TRADING_BASE = 'https://paper-api.alpaca.markets/v2'
const DATA_BASE = 'https://data.alpaca.markets/v2'

function authHeaders(credentials: Credentials): Record<string, string> {
  return {
    'APCA-API-KEY-ID': credentials.keyId,
    'APCA-API-SECRET-KEY': credentials.secret
  }
}

let assetCache: AssetSummary[] | null = null
let assetCacheCredentialsKey: string | null = null

async function ensureAssetCache(credentials: Credentials): Promise<AssetSummary[]> {
  const cacheKey = credentials.keyId
  if (assetCache && assetCacheCredentialsKey === cacheKey) return assetCache

  const res = await fetch(`${TRADING_BASE}/assets?status=active&asset_class=us_equity`, {
    headers: authHeaders(credentials)
  })
  if (!res.ok) throw new Error(`Failed to fetch assets: HTTP ${res.status}`)

  const raw = (await res.json()) as Array<{
    symbol: string
    name: string
    exchange: string
    tradable: boolean
  }>

  assetCache = raw
    .filter((a) => a.tradable)
    .map((a) => ({ symbol: a.symbol, name: a.name, exchange: a.exchange, tradable: a.tradable }))
  assetCacheCredentialsKey = cacheKey

  return assetCache
}

export async function searchAssets(
  credentials: Credentials,
  query: string,
  limit = 25
): Promise<AssetSummary[]> {
  const assets = await ensureAssetCache(credentials)
  const q = query.trim().toUpperCase()
  if (!q) return []

  const symbolMatches: AssetSummary[] = []
  const nameMatches: AssetSummary[] = []

  for (const asset of assets) {
    if (symbolMatches.length + nameMatches.length >= limit * 4) break
    if (asset.symbol.startsWith(q)) {
      symbolMatches.push(asset)
    } else if (asset.name.toUpperCase().includes(q)) {
      nameMatches.push(asset)
    }
  }

  symbolMatches.sort((a, b) => a.symbol.length - b.symbol.length)

  return [...symbolMatches, ...nameMatches].slice(0, limit)
}

export async function getLatestSnapshot(
  credentials: Credentials,
  symbol: string
): Promise<LatestSnapshot> {
  const headers = authHeaders(credentials)
  const [tradeRes, quoteRes, barRes] = await Promise.all([
    fetch(`${DATA_BASE}/stocks/${symbol}/trades/latest`, { headers }),
    fetch(`${DATA_BASE}/stocks/${symbol}/quotes/latest`, { headers }),
    fetch(`${DATA_BASE}/stocks/${symbol}/bars/latest`, { headers })
  ])

  const snapshot: LatestSnapshot = {}

  if (tradeRes.ok) {
    const { trade } = (await tradeRes.json()) as {
      trade?: { p: number; s: number; t: string }
    }
    if (trade) snapshot.trade = { symbol, price: trade.p, size: trade.s, timestamp: trade.t }
  }

  if (quoteRes.ok) {
    const { quote } = (await quoteRes.json()) as {
      quote?: { bp: number; bs: number; ap: number; as: number; t: string }
    }
    if (quote) {
      snapshot.quote = {
        symbol,
        bidPrice: quote.bp,
        bidSize: quote.bs,
        askPrice: quote.ap,
        askSize: quote.as,
        timestamp: quote.t
      }
    }
  }

  if (barRes.ok) {
    const { bar } = (await barRes.json()) as {
      bar?: { o: number; h: number; l: number; c: number; v: number; t: string }
    }
    if (bar) {
      snapshot.bar = {
        symbol,
        open: bar.o,
        high: bar.h,
        low: bar.l,
        close: bar.c,
        volume: bar.v,
        timestamp: bar.t
      }
    }
  }

  return snapshot
}
