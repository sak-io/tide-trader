// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import WatchlistPanel from './WatchlistPanel'

afterEach(cleanup)

type WatchlistApi = {
  listWatchlist: ReturnType<typeof vi.fn>
  addToWatchlist: ReturnType<typeof vi.fn>
  removeFromWatchlist: ReturnType<typeof vi.fn>
}

describe('WatchlistPanel', () => {
  beforeEach(() => {
    ;(window as unknown as { alpaca: WatchlistApi }).alpaca = {
      listWatchlist: vi.fn().mockResolvedValue([]),
      addToWatchlist: vi.fn(),
      removeFromWatchlist: vi.fn()
    }
  })

  it('loads and displays the persisted watchlist on mount', async () => {
    window.alpaca.listWatchlist = vi.fn().mockResolvedValue([
      { symbol: 'AAPL', addedAt: '2026-09-28T00:00:00Z' },
      { symbol: 'MSFT', addedAt: '2026-09-28T00:00:00Z' }
    ])

    render(<WatchlistPanel />)

    expect(await screen.findByText('AAPL')).toBeInTheDocument()
    expect(screen.getByText('MSFT')).toBeInTheDocument()
  })

  it('shows an empty state when the watchlist has no symbols', async () => {
    render(<WatchlistPanel />)

    expect(await screen.findByText(/no symbols on your watchlist yet/i)).toBeInTheDocument()
  })

  it('adds a symbol, uppercases it, and clears the input', async () => {
    window.alpaca.addToWatchlist = vi.fn().mockResolvedValue({ symbol: 'AAPL', addedAt: '2026-09-28T00:00:00Z' })

    render(<WatchlistPanel />)
    await screen.findByText(/no symbols on your watchlist yet/i)

    fireEvent.change(screen.getByPlaceholderText(/add a symbol/i), { target: { value: 'aapl' } })
    fireEvent.click(screen.getByRole('button', { name: /^add$/i }))

    await waitFor(() => expect(window.alpaca.addToWatchlist).toHaveBeenCalledWith('AAPL'))
    expect(await screen.findByText('AAPL')).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/add a symbol/i)).toHaveValue('')
  })

  it('removes a symbol from the list on Remove', async () => {
    window.alpaca.listWatchlist = vi.fn().mockResolvedValue([{ symbol: 'AAPL', addedAt: '2026-09-28T00:00:00Z' }])
    window.alpaca.removeFromWatchlist = vi.fn().mockResolvedValue(undefined)

    render(<WatchlistPanel />)
    await screen.findByText('AAPL')

    fireEvent.click(screen.getByRole('button', { name: /remove/i }))

    await waitFor(() => expect(window.alpaca.removeFromWatchlist).toHaveBeenCalledWith('AAPL'))
    expect(screen.queryByText('AAPL')).not.toBeInTheDocument()
  })

  it('shows an error banner when adding a symbol fails', async () => {
    window.alpaca.addToWatchlist = vi.fn().mockRejectedValue(new Error('Backend unreachable'))

    render(<WatchlistPanel />)
    await screen.findByText(/no symbols on your watchlist yet/i)

    fireEvent.change(screen.getByPlaceholderText(/add a symbol/i), { target: { value: 'AAPL' } })
    fireEvent.click(screen.getByRole('button', { name: /^add$/i }))

    expect(await screen.findByText('Backend unreachable')).toBeInTheDocument()
  })
})
