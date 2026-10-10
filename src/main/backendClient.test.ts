import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const readFileSync = vi.fn()

vi.mock('node:fs', () => ({ readFileSync }))

const {
  addToWatchlist,
  connectAlpaca,
  disconnectAlpaca,
  exportSuggestionsCsv,
  fetchMostActive,
  fetchWatchlist,
  getAlpacaStatus,
  removeFromWatchlist
} = await import('./backendClient')

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

describe('backendClient', () => {
  beforeEach(() => {
    readFileSync.mockReturnValue('the-access-token\n')
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('attaches the token read from the well-known access-token file as a bearer header', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(200, { connected: true }))

    await getAlpacaStatus()

    const [, init] = vi.mocked(fetch).mock.calls[0]
    expect((init?.headers as Record<string, string>).Authorization).toBe('Bearer the-access-token')
  })

  it('raises a clear error when the access-token file does not exist yet', async () => {
    readFileSync.mockImplementation(() => {
      throw new Error('ENOENT')
    })

    await expect(getAlpacaStatus()).rejects.toThrow(/backend running yet/i)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('raises a clear error when the backend is unreachable', async () => {
    vi.mocked(fetch).mockRejectedValue(new Error('connection refused'))

    await expect(fetchMostActive()).rejects.toThrow(/could not reach the tide trader backend/i)
  })

  it('connectAlpaca returns success:true on a 200 response', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(200, { connected: true }))

    const result = await connectAlpaca({ keyId: 'PKTEST', secret: 'shh' })

    expect(result).toEqual({ success: true })
    const [, init] = vi.mocked(fetch).mock.calls[0]
    expect(JSON.parse(init?.body as string)).toEqual({ api_key_id: 'PKTEST', secret_key: 'shh' })
  })

  it('connectAlpaca surfaces the backend-provided rejection reason on failure', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(400, { detail: 'access key verification failed' }))

    const result = await connectAlpaca({ keyId: 'PKBAD', secret: 'wrong' })

    expect(result).toEqual({ success: false, error: 'access key verification failed' })
  })

  it('disconnectAlpaca resolves on a 204 response with no body', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }))

    await expect(disconnectAlpaca()).resolves.toBeUndefined()
  })

  it('fetchWatchlist maps snake_case fields to camelCase', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(200, [{ symbol: 'AAPL', added_at: '2026-09-28T00:00:00Z' }]))

    const result = await fetchWatchlist()

    expect(result).toEqual([{ symbol: 'AAPL', addedAt: '2026-09-28T00:00:00Z' }])
  })

  it('addToWatchlist posts the symbol and maps the response', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(201, { symbol: 'MSFT', added_at: '2026-09-28T00:00:00Z' }))

    const result = await addToWatchlist('MSFT')

    const [, init] = vi.mocked(fetch).mock.calls[0]
    expect(JSON.parse(init?.body as string)).toEqual({ symbol: 'MSFT' })
    expect(result).toEqual({ symbol: 'MSFT', addedAt: '2026-09-28T00:00:00Z' })
  })

  it('removeFromWatchlist issues a DELETE to the encoded symbol path', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }))

    await removeFromWatchlist('AAPL')

    const [url, init] = vi.mocked(fetch).mock.calls[0]
    expect(url).toContain('/api/v1/watchlist/AAPL')
    expect(init?.method).toBe('DELETE')
  })

  it('exportSuggestionsCsv returns the raw CSV text, with hours appended to the query', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('id,symbol\n1,AAPL', { status: 200 }))

    const result = await exportSuggestionsCsv(24)

    const [url] = vi.mocked(fetch).mock.calls[0]
    expect(url).toContain('/api/v1/suggestions/export?hours=24')
    expect(result).toBe('id,symbol\n1,AAPL')
  })

  it('exportSuggestionsCsv omits the query entirely when no range is given', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('id,symbol', { status: 200 }))

    await exportSuggestionsCsv()

    const [url] = vi.mocked(fetch).mock.calls[0]
    expect(url).toBe('http://127.0.0.1:8000/api/v1/suggestions/export')
  })

  it('exportSuggestionsCsv surfaces the backend error detail on failure', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(500, { detail: 'boom' }))

    await expect(exportSuggestionsCsv()).rejects.toThrow('boom')
  })
})
