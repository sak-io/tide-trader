import { EventEmitter } from 'node:events'
import WebSocket from 'ws'
import type { BarUpdate, Credentials, QuoteUpdate, StreamStatus, TradeUpdate } from '../shared/types'

const STREAM_URL = 'wss://stream.data.alpaca.markets/v2/iex'
const RECONNECT_DELAY_MS = 3000

type AlpacaMessage =
  | { T: 'success' | 'error'; msg?: string; code?: number }
  | { T: 'subscription'; trades?: string[]; quotes?: string[]; bars?: string[] }
  | { T: 't'; S: string; p: number; s: number; t: string }
  | { T: 'q'; S: string; bp: number; bs: number; ap: number; as: number; t: string }
  | { T: 'b'; S: string; o: number; h: number; l: number; c: number; v: number; t: string }

export declare interface AlpacaStream {
  on(event: 'status', listener: (status: StreamStatus) => void): this
  on(event: 'trade', listener: (update: TradeUpdate) => void): this
  on(event: 'quote', listener: (update: QuoteUpdate) => void): this
  on(event: 'bar', listener: (update: BarUpdate) => void): this
}

export class AlpacaStream extends EventEmitter {
  private ws: WebSocket | null = null
  private credentials: Credentials | null = null
  private subscribed = new Set<string>()
  private status: StreamStatus = 'disconnected'
  private reconnectTimer: NodeJS.Timeout | null = null
  private intentionalClose = false

  connect(credentials: Credentials): void {
    this.credentials = credentials
    this.intentionalClose = false
    this.open()
  }

  disconnect(): void {
    this.intentionalClose = true
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.ws?.close()
    this.ws = null
    this.setStatus('disconnected')
  }

  subscribeSymbol(symbol: string): void {
    if (this.subscribed.has(symbol)) return
    this.subscribed.add(symbol)
    this.sendSubscribe([symbol])
  }

  unsubscribeSymbol(symbol: string): void {
    if (!this.subscribed.has(symbol)) return
    this.subscribed.delete(symbol)
    this.send({ action: 'unsubscribe', trades: [symbol], quotes: [symbol], bars: [symbol] })
  }

  private open(): void {
    if (!this.credentials) return
    this.setStatus('connecting')

    this.ws = new WebSocket(STREAM_URL)

    this.ws.on('open', () => {
      this.send({
        action: 'auth',
        key: this.credentials!.keyId,
        secret: this.credentials!.secret
      })
    })

    this.ws.on('message', (data) => this.handleMessage(data.toString()))

    this.ws.on('close', () => {
      if (this.intentionalClose) return
      this.setStatus('disconnected')
      this.scheduleReconnect()
    })

    this.ws.on('error', () => {
      this.setStatus('error')
    })
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.open()
    }, RECONNECT_DELAY_MS)
  }

  private handleMessage(raw: string): void {
    let messages: AlpacaMessage[]
    try {
      messages = JSON.parse(raw)
    } catch {
      return
    }

    for (const msg of messages) {
      switch (msg.T) {
        case 'success':
          if (msg.msg === 'authenticated') {
            this.setStatus('connected')
            if (this.subscribed.size > 0) this.sendSubscribe([...this.subscribed])
          }
          break
        case 'error':
          this.setStatus('auth_failed')
          break
        case 't':
          this.emit('trade', {
            symbol: msg.S,
            price: msg.p,
            size: msg.s,
            timestamp: msg.t
          } satisfies TradeUpdate)
          break
        case 'q':
          this.emit('quote', {
            symbol: msg.S,
            bidPrice: msg.bp,
            bidSize: msg.bs,
            askPrice: msg.ap,
            askSize: msg.as,
            timestamp: msg.t
          } satisfies QuoteUpdate)
          break
        case 'b':
          this.emit('bar', {
            symbol: msg.S,
            open: msg.o,
            high: msg.h,
            low: msg.l,
            close: msg.c,
            volume: msg.v,
            timestamp: msg.t
          } satisfies BarUpdate)
          break
      }
    }
  }

  private sendSubscribe(symbols: string[]): void {
    this.send({ action: 'subscribe', trades: symbols, quotes: symbols, bars: symbols })
  }

  private send(payload: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload))
    }
  }

  private setStatus(status: StreamStatus): void {
    this.status = status
    this.emit('status', status)
  }

  getStatus(): StreamStatus {
    return this.status
  }
}
