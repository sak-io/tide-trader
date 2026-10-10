import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Suggestion } from '../shared/types'

const fetchSuggestions = vi.fn()

vi.mock('./backendClient', () => ({ fetchSuggestions }))

const { SuggestionsPoller } = await import('./suggestionsPoller')

function suggestion(id: number): Suggestion {
  return {
    id,
    symbol: 'AAPL',
    direction: 'bullish',
    price: 190,
    score: 85,
    stopPrice: 185,
    targetPrice: 199,
    outcome: 'open',
    outcomePrice: null,
    outcomeAt: null,
    lastPrice: null,
    returnPct: null,
    indicators: { smaFast: 105, smaSlow: 102, rsi14: 60, volumeRatio: 2 },
    triggeredRules: ['golden_cross_sma20_sma50'],
    sources: ['watchlist'],
    rationale: 'Strong setup.',
    status: 'pending',
    generatedAt: '2026-09-28T00:00:00Z',
    updatedAt: '2026-09-28T00:00:00Z'
  }
}

describe('SuggestionsPoller', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    fetchSuggestions.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('does not emit for suggestions that already existed on the first poll', async () => {
    fetchSuggestions.mockResolvedValue([suggestion(1)])
    const poller = new SuggestionsPoller()
    const onNew = vi.fn()
    poller.on('new-suggestions', onNew)

    poller.start(1000)
    await vi.waitFor(() => expect(fetchSuggestions).toHaveBeenCalledTimes(1))

    expect(onNew).not.toHaveBeenCalled()
    poller.stop()
  })

  it('emits only newly-seen suggestions on later polls', async () => {
    fetchSuggestions.mockResolvedValueOnce([suggestion(1)])
    const poller = new SuggestionsPoller()
    const onNew = vi.fn()
    poller.on('new-suggestions', onNew)

    poller.start(1000)
    await vi.waitFor(() => expect(fetchSuggestions).toHaveBeenCalledTimes(1))
    expect(onNew).not.toHaveBeenCalled()

    fetchSuggestions.mockResolvedValueOnce([suggestion(1), suggestion(2)])
    await vi.advanceTimersByTimeAsync(1000)

    expect(onNew).toHaveBeenCalledTimes(1)
    expect(onNew).toHaveBeenCalledWith([suggestion(2)])

    poller.stop()
  })

  it('does not crash the poll loop when the backend request fails', async () => {
    fetchSuggestions.mockRejectedValueOnce(new Error('backend unreachable'))
    const poller = new SuggestionsPoller()
    const onNew = vi.fn()
    poller.on('new-suggestions', onNew)

    poller.start(1000)
    await vi.waitFor(() => expect(fetchSuggestions).toHaveBeenCalledTimes(1))

    fetchSuggestions.mockResolvedValueOnce([suggestion(1)])
    await vi.advanceTimersByTimeAsync(1000)
    await vi.waitFor(() => expect(fetchSuggestions).toHaveBeenCalledTimes(2))

    // First poll failed (nothing seeded), second poll succeeds and seeds - so the
    // suggestion from that second poll is treated as the initial seed, not "new".
    expect(onNew).not.toHaveBeenCalled()

    poller.stop()
  })

  it('start() is idempotent while already running', () => {
    fetchSuggestions.mockResolvedValue([])
    const poller = new SuggestionsPoller()

    poller.start(1000)
    poller.start(1000)
    poller.stop()

    expect(fetchSuggestions).toHaveBeenCalledTimes(1)
  })
})
