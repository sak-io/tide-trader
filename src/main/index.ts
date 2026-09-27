import { app, BrowserWindow, ipcMain, shell } from 'electron'
import { join } from 'node:path'
import { clearCredentials, loadCredentials, saveCredentials } from './config'
import { getLatestSnapshot, searchAssets, validateCredentials } from './alpacaRest'
import { fetchBars, fetchMostActive, fetchMovers } from './backendClient'
import { AlpacaStream } from './alpacaStream'
import type { BarTimeframe, ConfigStatus, Credentials, SaveCredentialsResult } from '../shared/types'

const stream = new AlpacaStream()
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
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false
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

function registerIpcHandlers(): void {
  ipcMain.handle('alpaca:get-config-status', (): ConfigStatus => {
    const creds = loadCredentials()
    return creds ? { configured: true, keyId: creds.keyId } : { configured: false }
  })

  ipcMain.handle(
    'alpaca:save-credentials',
    async (_event, credentials: Credentials): Promise<SaveCredentialsResult> => {
      const result = await validateCredentials(credentials)
      if (!result.valid) return { success: false, error: result.error }

      saveCredentials(credentials)
      stream.connect(credentials)
      return { success: true }
    }
  )

  ipcMain.handle('alpaca:clear-credentials', () => {
    stream.disconnect()
    clearCredentials()
  })

  ipcMain.handle('alpaca:search-assets', async (_event, query: string) => {
    const creds = loadCredentials()
    if (!creds) return []
    return searchAssets(creds, query)
  })

  ipcMain.handle('alpaca:subscribe', (_event, symbol: string) => {
    stream.subscribeSymbol(symbol)
  })

  ipcMain.handle('alpaca:get-latest', async (_event, symbol: string) => {
    const creds = loadCredentials()
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
}

app.whenReady().then(() => {
  registerIpcHandlers()
  forwardStreamEvents()
  createWindow()

  const creds = loadCredentials()
  if (creds) stream.connect(creds)

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  stream.disconnect()
})
