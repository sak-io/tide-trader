import { EventEmitter } from 'node:events'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

class FakeWebSocket extends EventEmitter {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3

  readyState = FakeWebSocket.CONNECTING
  sent: string[] = []

  constructor(public url: string) {
    super()
    createdSockets.push(this)
  }

  send(data: string): void {
    this.sent.push(data)
  }

  close(): void {
    this.readyState = FakeWebSocket.CLOSED
    this.emit('close')
  }

  /** Test helper: simulate the server accepting the connection. */
  simulateOpen(): void {
    this.readyState = FakeWebSocket.OPEN
    this.emit('open')
  }

  /** Test helper: simulate a message frame from the server. */
  simulateMessage(payload: unknown): void {
    this.emit('message', Buffer.from(JSON.stringify(payload)))
  }
}

let createdSockets: FakeWebSocket[]

vi.mock('ws', () => ({ default: FakeWebSocket }))

const { AlpacaStream } = await import('./alpacaStream')

function lastSocket(): FakeWebSocket {
  return createdSockets[createdSockets.length - 1]
}

function lastSentPayload(socket: FakeWebSocket): unknown {
  return JSON.parse(socket.sent[socket.sent.length - 1])
}

describe('AlpacaStream', () => {
  beforeEach(() => {
    createdSockets = []
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('sends an auth frame once the socket opens', () => {
    const stream = new AlpacaStream()
    stream.connect({ keyId: 'PKTEST', secret: 'shh' })

    lastSocket().simulateOpen()

    expect(lastSentPayload(lastSocket())).toEqual({ action: 'auth', key: 'PKTEST', secret: 'shh' })
  })

  it('reports connected status once authenticated', () => {
    const stream = new AlpacaStream()
    const statuses: string[] = []
    stream.on('status', (status) => statuses.push(status))

    stream.connect({ keyId: 'PKTEST', secret: 'shh' })
    lastSocket().simulateOpen()
    lastSocket().simulateMessage([{ T: 'success', msg: 'authenticated' }])

    expect(statuses).toEqual(['connecting', 'connected'])
  })

  it('reports auth_failed on an error frame', () => {
    const stream = new AlpacaStream()
    const statuses: string[] = []
    stream.on('status', (status) => statuses.push(status))

    stream.connect({ keyId: 'bad', secret: 'creds' })
    lastSocket().simulateOpen()
    lastSocket().simulateMessage([{ T: 'error', code: 401, msg: 'not authorized' }])

    expect(statuses).toEqual(['connecting', 'auth_failed'])
  })

  it('parses trade, quote, and bar messages into the expected shapes', () => {
    const stream = new AlpacaStream()
    const trades: unknown[] = []
    const quotes: unknown[] = []
    const bars: unknown[] = []
    stream.on('trade', (u) => trades.push(u))
    stream.on('quote', (u) => quotes.push(u))
    stream.on('bar', (u) => bars.push(u))

    stream.connect({ keyId: 'k', secret: 's' })
    lastSocket().simulateOpen()
    lastSocket().simulateMessage([
      { T: 't', S: 'AAPL', p: 190.5, s: 100, t: '2026-09-27T00:00:00Z' },
      { T: 'q', S: 'AAPL', bp: 190.0, bs: 1, ap: 190.5, as: 2, t: '2026-09-27T00:00:01Z' },
      { T: 'b', S: 'AAPL', o: 190, h: 191, l: 189, c: 190.5, v: 1000, t: '2026-09-27T00:00:02Z' }
    ])

    expect(trades).toEqual([{ symbol: 'AAPL', price: 190.5, size: 100, timestamp: '2026-09-27T00:00:00Z' }])
    expect(quotes).toEqual([
      { symbol: 'AAPL', bidPrice: 190.0, bidSize: 1, askPrice: 190.5, askSize: 2, timestamp: '2026-09-27T00:00:01Z' }
    ])
    expect(bars).toEqual([
      { symbol: 'AAPL', open: 190, high: 191, low: 189, close: 190.5, volume: 1000, timestamp: '2026-09-27T00:00:02Z' }
    ])
  })

  it('ignores a malformed (non-JSON) message instead of throwing', () => {
    const stream = new AlpacaStream()
    stream.connect({ keyId: 'k', secret: 's' })
    lastSocket().simulateOpen()

    expect(() => lastSocket().emit('message', Buffer.from('not json'))).not.toThrow()
  })

  it('re-subscribes to previously subscribed symbols once (re)authenticated', () => {
    const stream = new AlpacaStream()
    stream.connect({ keyId: 'k', secret: 's' })
    lastSocket().simulateOpen()
    stream.subscribeSymbol('AAPL')

    lastSocket().simulateMessage([{ T: 'success', msg: 'authenticated' }])

    expect(lastSentPayload(lastSocket())).toEqual({
      action: 'subscribe',
      trades: ['AAPL'],
      quotes: ['AAPL'],
      bars: ['AAPL']
    })
  })

  it('does not resend a subscribe frame for a symbol already subscribed', () => {
    const stream = new AlpacaStream()
    stream.connect({ keyId: 'k', secret: 's' })
    lastSocket().simulateOpen()
    lastSocket().simulateMessage([{ T: 'success', msg: 'authenticated' }])

    const sentCountBefore = lastSocket().sent.length
    stream.subscribeSymbol('AAPL')
    stream.subscribeSymbol('AAPL') // second call for the same symbol should be a no-op

    expect(lastSocket().sent.length).toBe(sentCountBefore + 1)
  })

  it('sends an unsubscribe frame and stops tracking the symbol', () => {
    const stream = new AlpacaStream()
    stream.connect({ keyId: 'k', secret: 's' })
    lastSocket().simulateOpen()
    lastSocket().simulateMessage([{ T: 'success', msg: 'authenticated' }])
    stream.subscribeSymbol('AAPL')

    stream.unsubscribeSymbol('AAPL')

    expect(lastSentPayload(lastSocket())).toEqual({
      action: 'unsubscribe',
      trades: ['AAPL'],
      quotes: ['AAPL'],
      bars: ['AAPL']
    })
  })

  it('reconnects automatically after an unintentional close', () => {
    const stream = new AlpacaStream()
    stream.connect({ keyId: 'k', secret: 's' })
    const firstSocket = lastSocket()
    firstSocket.simulateOpen()

    firstSocket.emit('close') // server-initiated / network drop, not stream.disconnect()

    expect(createdSockets).toHaveLength(1) // no reconnect attempt yet
    vi.advanceTimersByTime(3000)
    expect(createdSockets).toHaveLength(2) // reconnected
  })

  it('does not reconnect after an intentional disconnect', () => {
    const stream = new AlpacaStream()
    stream.connect({ keyId: 'k', secret: 's' })
    lastSocket().simulateOpen()

    stream.disconnect()
    vi.advanceTimersByTime(10_000)

    expect(createdSockets).toHaveLength(1)
    expect(stream.getStatus()).toBe('disconnected')
  })

  it('re-authenticates with the same credentials after reconnecting', () => {
    const stream = new AlpacaStream()
    stream.connect({ keyId: 'PKTEST', secret: 'shh' })
    lastSocket().simulateOpen()
    lastSocket().emit('close')

    vi.advanceTimersByTime(3000)
    lastSocket().simulateOpen()

    expect(lastSentPayload(lastSocket())).toEqual({ action: 'auth', key: 'PKTEST', secret: 'shh' })
  })
})
