// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import SuggestionsPanel from './SuggestionsPanel'
import type { Suggestion } from '../../../shared/types'

afterEach(cleanup)

const suggestion: Suggestion = {
  id: 1,
  symbol: 'AAPL',
  direction: 'bullish',
  price: 190.5,
  score: 82,
  stopPrice: 185,
  targetPrice: 199,
  outcome: 'open',
  outcomePrice: null,
  outcomeAt: null,
  lastPrice: 192,
  returnPct: 0.8,
  indicators: { smaFast: 105, smaSlow: 102, rsi14: 55, volumeRatio: 1.8 },
  triggeredRules: ['golden_cross_sma20_sma50'],
  sources: ['watchlist'],
  rationale: 'Strong momentum.',
  status: 'pending',
  generatedAt: '2026-09-28T00:00:00Z',
  updatedAt: '2026-09-28T00:00:00Z'
}

type SuggestionsApi = {
  listSuggestions: ReturnType<typeof vi.fn>
  getSuggestionPerformance: ReturnType<typeof vi.fn>
  dismissSuggestion: ReturnType<typeof vi.fn>
  exportSuggestions: ReturnType<typeof vi.fn>
  onNewSuggestion: ReturnType<typeof vi.fn>
}

describe('SuggestionsPanel', () => {
  beforeEach(() => {
    ;(window as unknown as { alpaca: SuggestionsApi }).alpaca = {
      listSuggestions: vi.fn().mockResolvedValue([]),
      getSuggestionPerformance: vi.fn().mockResolvedValue({
        total: 0, open: 0, targetHit: 0, stopped: 0, expired: 0, winRatePct: null, avgReturnPct: null
      }),
      dismissSuggestion: vi.fn(),
      exportSuggestions: vi.fn(),
      onNewSuggestion: vi.fn().mockReturnValue(() => {})
    }
  })

  it('shows the empty state when there are no pending suggestions', async () => {
    render(<SuggestionsPanel />)
    expect(await screen.findByText(/no pending suggestions/i)).toBeInTheDocument()
  })

  it('renders a suggestion and dismisses it on click', async () => {
    window.alpaca.listSuggestions = vi.fn().mockResolvedValue([suggestion])
    window.alpaca.dismissSuggestion = vi.fn().mockResolvedValue({ ...suggestion, status: 'dismissed' })

    render(<SuggestionsPanel />)
    await screen.findByText('AAPL')

    fireEvent.click(screen.getByRole('button', { name: /dismiss/i }))

    await waitFor(() => expect(window.alpaca.dismissSuggestion).toHaveBeenCalledWith(1))
    expect(screen.queryByText('AAPL')).not.toBeInTheDocument()
  })

  it('shows stop, target, outcome and live return for a suggestion', async () => {
    window.alpaca.listSuggestions = vi.fn().mockResolvedValue([
      suggestion,
      { ...suggestion, id: 2, symbol: 'MSFT', outcome: 'stopped', outcomePrice: 185, returnPct: -2.9 }
    ])

    render(<SuggestionsPanel />)
    await screen.findByText('AAPL')

    expect(screen.getAllByText('Stop $185.00')).toHaveLength(2)
    expect(screen.getAllByText('Target $199.00')).toHaveLength(2)
    expect(screen.getByText('Open')).toBeInTheDocument()
    expect(screen.getByText('+0.8%')).toBeInTheDocument()
    expect(screen.getByText('Stopped out')).toBeInTheDocument()
    expect(screen.getByText('-2.9%')).toHaveClass('return-negative')
  })

  it('shows the performance summary once suggestions are tracked', async () => {
    window.alpaca.getSuggestionPerformance = vi.fn().mockResolvedValue({
      total: 4, open: 1, targetHit: 2, stopped: 1, expired: 0, winRatePct: 66.7, avgReturnPct: 3.2
    })

    render(<SuggestionsPanel />)

    expect(await screen.findByText('4 tracked')).toBeInTheDocument()
    expect(screen.getByText('Win rate 67%')).toBeInTheDocument()
    expect(screen.getByText('Avg +3.2%')).toBeInTheDocument()
  })

  it('still lists suggestions when the performance summary fails', async () => {
    window.alpaca.listSuggestions = vi.fn().mockResolvedValue([suggestion])
    window.alpaca.getSuggestionPerformance = vi.fn().mockRejectedValue(new Error('nope'))

    render(<SuggestionsPanel />)

    expect(await screen.findByText('AAPL')).toBeInTheDocument()
  })

  it('downloads the last 24h with the correct hours value and shows the saved path', async () => {
    window.alpaca.exportSuggestions = vi.fn().mockResolvedValue({ success: true, path: '/tmp/suggestions_last_24h.csv' })

    render(<SuggestionsPanel />)
    await screen.findByText(/no pending suggestions/i)

    fireEvent.click(screen.getByRole('button', { name: '24h' }))

    await waitFor(() => expect(window.alpaca.exportSuggestions).toHaveBeenCalledWith(24))
    expect(await screen.findByText(/saved to \/tmp\/suggestions_last_24h\.csv/i)).toBeInTheDocument()
  })

  it('downloads "All" with no hours argument', async () => {
    window.alpaca.exportSuggestions = vi.fn().mockResolvedValue({ success: true, path: '/tmp/suggestions_all.csv' })

    render(<SuggestionsPanel />)
    await screen.findByText(/no pending suggestions/i)

    fireEvent.click(screen.getByRole('button', { name: 'All' }))

    await waitFor(() => expect(window.alpaca.exportSuggestions).toHaveBeenCalledWith(undefined))
  })

  it('shows the error message when export fails', async () => {
    window.alpaca.exportSuggestions = vi.fn().mockResolvedValue({ success: false, error: 'Backend unreachable' })

    render(<SuggestionsPanel />)
    await screen.findByText(/no pending suggestions/i)

    fireEvent.click(screen.getByRole('button', { name: '7d' }))

    expect(await screen.findByText('Backend unreachable')).toBeInTheDocument()
  })
})
