import { useEffect, useState } from 'react'
import CredentialsForm from './components/CredentialsForm'
import SearchBar from './components/SearchBar'
import DiscoverPanel from './components/DiscoverPanel'
import SuggestionsPanel from './components/SuggestionsPanel'
import SymbolDetail from './components/SymbolDetail'
import WatchlistPanel from './components/WatchlistPanel'
import type { AssetSummary, StreamStatus } from '../../shared/types'

const SELECTED_SYMBOL_STORAGE_KEY = 'tide-trader:selected-symbol'

const statusLabel: Record<StreamStatus, string> = {
  disconnected: 'Disconnected',
  connecting: 'Connecting…',
  connected: 'Live',
  auth_failed: 'Auth failed',
  error: 'Connection error'
}

export default function App(): JSX.Element {
  const [checkingConfig, setCheckingConfig] = useState(true)
  const [configured, setConfigured] = useState(false)
  const [streamStatus, setStreamStatus] = useState<StreamStatus>('disconnected')
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)

  useEffect(() => {
    window.alpaca.getStatus().then((status) => {
      setConfigured(status.connected)
      setCheckingConfig(false)
      if (status.connected) {
        setSelectedSymbol(localStorage.getItem(SELECTED_SYMBOL_STORAGE_KEY))
      }
    })
  }, [])

  useEffect(() => {
    if (!configured) return

    window.alpaca.getStreamStatus().then(setStreamStatus)
    const unsubStatus = window.alpaca.onStreamStatus(setStreamStatus)

    return () => unsubStatus()
  }, [configured])

  function handleSelectSymbol(symbol: string): void {
    setSelectedSymbol(symbol)
    localStorage.setItem(SELECTED_SYMBOL_STORAGE_KEY, symbol)
  }

  function handleSelectAsset(asset: AssetSummary): void {
    handleSelectSymbol(asset.symbol)
  }

  async function handleDisconnectAccount(): Promise<void> {
    await window.alpaca.clearCredentials()
    setConfigured(false)
    setSelectedSymbol(null)
  }

  if (checkingConfig) return <div className="loading-screen">Loading…</div>

  if (!configured) {
    return <CredentialsForm onSaved={() => setConfigured(true)} />
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>Tide Trader</h1>
        <div className="header-actions">
          <span className={`status-pill status-${streamStatus}`}>
            <span className="dot" />
            {statusLabel[streamStatus]}
          </span>
          <button className="link-btn" onClick={handleDisconnectAccount}>
            Change API keys
          </button>
        </div>
      </header>

      <SuggestionsPanel />

      <SearchBar onSelect={handleSelectAsset} />

      <div className="dashboard">
        <div className="dashboard-sidebar">
          <DiscoverPanel selectedSymbol={selectedSymbol} onSelect={handleSelectSymbol} />
          <WatchlistPanel />
        </div>

        {selectedSymbol ? (
          <SymbolDetail key={selectedSymbol} symbol={selectedSymbol} />
        ) : (
          <div className="empty-state">
            Pick a stock from Most Active / Gainers / Losers, or search for one above, to see its
            price history.
          </div>
        )}
      </div>
    </div>
  )
}
