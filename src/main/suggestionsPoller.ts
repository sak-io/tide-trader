import { EventEmitter } from 'node:events'
import { fetchSuggestions } from './backendClient'
import type { Suggestion } from '../shared/types'

const DEFAULT_POLL_INTERVAL_MS = 60_000

export declare interface SuggestionsPoller {
  on(event: 'new-suggestions', listener: (suggestions: Suggestion[]) => void): this
}

/** Polls pending suggestions from the backend and reports newly-seen ones.
 *
 * There's no push channel from the backend for this (unlike the Alpaca WS relay),
 * so this just diffs each poll's pending IDs against what it's already reported.
 */
export class SuggestionsPoller extends EventEmitter {
  private timer: NodeJS.Timeout | null = null
  private seenIds = new Set<number>()
  private initialized = false
  private polling = false

  start(intervalMs = DEFAULT_POLL_INTERVAL_MS): void {
    if (this.timer) return
    this.poll()
    this.timer = setInterval(() => this.poll(), intervalMs)
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer)
    this.timer = null
  }

  private async poll(): Promise<void> {
    if (this.polling) return
    this.polling = true

    try {
      const suggestions = await fetchSuggestions('pending')

      if (!this.initialized) {
        // Seed seen IDs on the very first poll without notifying - avoids a burst
        // of "new" notifications for suggestions that already existed before this
        // Electron process launched.
        for (const suggestion of suggestions) this.seenIds.add(suggestion.id)
        this.initialized = true
        return
      }

      const newOnes = suggestions.filter((suggestion) => !this.seenIds.has(suggestion.id))
      for (const suggestion of suggestions) this.seenIds.add(suggestion.id)

      if (newOnes.length > 0) this.emit('new-suggestions', newOnes)
    } catch {
      // Best-effort: a transient backend hiccup shouldn't crash the poller - it
      // just tries again on the next interval.
    } finally {
      this.polling = false
    }
  }
}
