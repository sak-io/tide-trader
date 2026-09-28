import { contextBridge, ipcRenderer } from 'electron'
import type {
  ActiveTicker,
  AlpacaStatus,
  AssetSummary,
  BarTimeframe,
  BarUpdate,
  Credentials,
  HistoricalBar,
  LatestSnapshot,
  MarketMovers,
  QuoteUpdate,
  SaveCredentialsResult,
  StreamStatus,
  Suggestion,
  SuggestionStatus,
  TradeUpdate
} from '../shared/types'

const api = {
  getStatus: (): Promise<AlpacaStatus> => ipcRenderer.invoke('alpaca:get-status'),
  saveCredentials: (credentials: Credentials): Promise<SaveCredentialsResult> =>
    ipcRenderer.invoke('alpaca:save-credentials', credentials),
  clearCredentials: (): Promise<void> => ipcRenderer.invoke('alpaca:clear-credentials'),
  searchAssets: (query: string): Promise<AssetSummary[]> =>
    ipcRenderer.invoke('alpaca:search-assets', query),
  subscribe: (symbol: string): Promise<void> => ipcRenderer.invoke('alpaca:subscribe', symbol),
  getLatest: (symbol: string): Promise<LatestSnapshot> =>
    ipcRenderer.invoke('alpaca:get-latest', symbol),
  unsubscribe: (symbol: string): Promise<void> =>
    ipcRenderer.invoke('alpaca:unsubscribe', symbol),
  getStreamStatus: (): Promise<StreamStatus> => ipcRenderer.invoke('alpaca:get-stream-status'),

  getMostActive: (top?: number): Promise<ActiveTicker[]> => ipcRenderer.invoke('market:most-active', top),
  getMovers: (top?: number): Promise<MarketMovers> => ipcRenderer.invoke('market:movers', top),
  getBars: (symbol: string, timeframe?: BarTimeframe, limit?: number): Promise<HistoricalBar[]> =>
    ipcRenderer.invoke('market:bars', symbol, timeframe, limit),

  listSuggestions: (status?: SuggestionStatus | 'all'): Promise<Suggestion[]> =>
    ipcRenderer.invoke('suggestions:list', status),
  dismissSuggestion: (id: number): Promise<Suggestion> => ipcRenderer.invoke('suggestions:dismiss', id),
  onNewSuggestion: (callback: (suggestions: Suggestion[]) => void): (() => void) => {
    const listener = (_event: Electron.IpcRendererEvent, suggestions: Suggestion[]): void =>
      callback(suggestions)
    ipcRenderer.on('suggestions:new', listener)
    return () => ipcRenderer.removeListener('suggestions:new', listener)
  },

  onStreamStatus: (callback: (status: StreamStatus) => void): (() => void) => {
    const listener = (_event: Electron.IpcRendererEvent, status: StreamStatus): void =>
      callback(status)
    ipcRenderer.on('alpaca:stream-status', listener)
    return () => ipcRenderer.removeListener('alpaca:stream-status', listener)
  },
  onTrade: (callback: (update: TradeUpdate) => void): (() => void) => {
    const listener = (_event: Electron.IpcRendererEvent, update: TradeUpdate): void =>
      callback(update)
    ipcRenderer.on('alpaca:trade', listener)
    return () => ipcRenderer.removeListener('alpaca:trade', listener)
  },
  onQuote: (callback: (update: QuoteUpdate) => void): (() => void) => {
    const listener = (_event: Electron.IpcRendererEvent, update: QuoteUpdate): void =>
      callback(update)
    ipcRenderer.on('alpaca:quote', listener)
    return () => ipcRenderer.removeListener('alpaca:quote', listener)
  },
  onBar: (callback: (update: BarUpdate) => void): (() => void) => {
    const listener = (_event: Electron.IpcRendererEvent, update: BarUpdate): void =>
      callback(update)
    ipcRenderer.on('alpaca:bar', listener)
    return () => ipcRenderer.removeListener('alpaca:bar', listener)
  }
}

contextBridge.exposeInMainWorld('alpaca', api)

export type AlpacaApi = typeof api
