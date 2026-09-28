import { app, BrowserWindow, dialog, ipcMain, Notification, shell } from 'electron'
import { writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import * as alpacaCredentialCache from './alpacaCredentialCache'
import { getLatestSnapshot, searchAssets } from './alpacaRest'
import {
  addToWatchlist,
  connectAlpaca,
  dismissSuggestion,
  disconnectAlpaca,
  exportSuggestionsCsv,
  fetchBars,
  fetchMostActive,
  fetchMovers,
  fetchSuggestions,
  fetchWatchlist,
  getAlpacaStatus,
  removeFromWatchlist
} from './backendClient'
import { AlpacaStream } from './alpacaStream'
import { SuggestionsPoller } from './suggestionsPoller'
import type {
  AlpacaStatus,
  BarTimeframe,
  Credentials,
  ExportSuggestionsResult,
  SaveCredentialsResult,
  SuggestionStatus
} from '../shared/types'

const stream = new AlpacaStream()
const suggestionsPoller = new SuggestionsPoller()
let mainWindow: BrowserWindow | null = null

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 750,
    minWidth: 800,
    minHeight: 560,
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js')
    }
  })

  mainWindow.on('ready-to-show', () => mainWindow?.show())

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  if (process.env.ELECTRON_RENDERER_URL) {
    mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

function forwardStreamEvents(): void {
  stream.on('status', (status) => mainWindow?.webContents.send('alpaca:stream-status', status))
  stream.on('trade', (update) => mainWindow?.webContents.send('alpaca:trade', update))
  stream.on('quote', (update) => mainWindow?.webContents.send('alpaca:quote', update))
  stream.on('bar', (update) => mainWindow?.webContents.send('alpaca:bar', update))
}

function forwardSuggestionEvents(): void {
  suggestionsPoller.on('new-suggestions', (suggestions) => {
    mainWindow?.webContents.send('suggestions:new', suggestions)

    for (const suggestion of suggestions) {
      new Notification({
        title: `New ${suggestion.direction} suggestion: ${suggestion.symbol}`,
        body: suggestion.rationale ?? `Composite score ${Math.round(suggestion.score)}/100`
      }).show()
    }
  })
}

function registerIpcHandlers(): void {
  ipcMain.handle('alpaca:get-status', async (): Promise<AlpacaStatus> => {
    try {
      return await getAlpacaStatus()
    } catch {
      // Most commonly: the backend isn't running yet, or hasn't finished starting up.
      // Treat that the same as "not connected" here - CredentialsForm's own submit
      // path surfaces the specific "is the backend running?" error instead.
      return { connected: false }
    }
  })

  ipcMain.handle(
    'alpaca:save-credentials',
    async (_event, credentials: Credentials): Promise<SaveCredentialsResult> => {
      const result = await connectAlpaca(credentials)
      if (!result.success) return result

      // The backend now holds this credential in its own memory for order/account
      // calls. Electron's direct-to-Alpaca streaming path is a separate process with
      // no way to read it back from the backend (by design - no "reveal" shortcut
      // between the two), so it needs its own in-memory copy too.
      alpacaCredentialCache.set(credentials)
      stream.connect(credentials)
      return { success: true }
    }
  )

  ipcMain.handle('alpaca:clear-credentials', async () => {
    stream.disconnect()
    alpacaCredentialCache.clear()
    await disconnectAlpaca().catch(() => {
      // Best-effort: if the backend is already unreachable, there's nothing to
      // disconnect there anyway - the local, in-memory state is cleared regardless.
    })
  })

  ipcMain.handle('alpaca:search-assets', async (_event, query: string) => {
    const creds = alpacaCredentialCache.get()
    if (!creds) return []
    return searchAssets(creds, query)
  })

  ipcMain.handle('alpaca:subscribe', (_event, symbol: string) => {
    stream.subscribeSymbol(symbol)
  })

  ipcMain.handle('alpaca:get-latest', async (_event, symbol: string) => {
    const creds = alpacaCredentialCache.get()
    if (!creds) return {}
    try {
      return await getLatestSnapshot(creds, symbol)
    } catch {
      return {}
    }
  })

  ipcMain.handle('alpaca:unsubscribe', (_event, symbol: string) => {
    stream.unsubscribeSymbol(symbol)
  })

  ipcMain.handle('alpaca:get-stream-status', () => stream.getStatus())

  ipcMain.handle('market:most-active', (_event, top?: number) => fetchMostActive(top))
  ipcMain.handle('market:movers', (_event, top?: number) => fetchMovers(top))
  ipcMain.handle('market:bars', (_event, symbol: string, timeframe?: BarTimeframe, limit?: number) =>
    fetchBars(symbol, timeframe, limit)
  )

  ipcMain.handle('suggestions:list', (_event, status?: SuggestionStatus | 'all') => fetchSuggestions(status))
  ipcMain.handle('suggestions:dismiss', (_event, id: number) => dismissSuggestion(id))

  ipcMain.handle('suggestions:export', async (_event, hours?: number): Promise<ExportSuggestionsResult> => {
    try {
      const csv = await exportSuggestionsCsv(hours)
      const defaultName = hours ? `suggestions_last_${hours}h.csv` : 'suggestions_all.csv'
      const { canceled, filePath } = await dialog.showSaveDialog({
        title: 'Save Trade Suggestions',
        defaultPath: defaultName,
        filters: [{ name: 'CSV', extensions: ['csv'] }]
      })
      if (canceled || !filePath) return { success: false }

      await writeFile(filePath, csv, 'utf-8')
      return { success: true, path: filePath }
    } catch (err) {
      return { success: false, error: err instanceof Error ? err.message : 'Unknown error' }
    }
  })

  ipcMain.handle('watchlist:list', () => fetchWatchlist())
  ipcMain.handle('watchlist:add', (_event, symbol: string) => addToWatchlist(symbol))
  ipcMain.handle('watchlist:remove', (_event, symbol: string) => removeFromWatchlist(symbol))
}

app.whenReady().then(() => {
  registerIpcHandlers()
  forwardStreamEvents()
  forwardSuggestionEvents()
  createWindow()
  suggestionsPoller.start()

  // Note: no auto-reconnect of the direct-to-Alpaca stream here. Credentials are
  // in-memory only (alpacaCredentialCache starts empty every launch), so even if the
  // backend still holds a live connection from before this Electron process started,
  // the realtime stream needs the user to go through CredentialsForm again to get a
  // fresh copy of the secret - see docs/ARCHITECTURE.md.

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  stream.disconnect()
  suggestionsPoller.stop()
})
