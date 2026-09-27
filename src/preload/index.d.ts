import type { AlpacaApi } from './index'

declare global {
  interface Window {
    alpaca: AlpacaApi
  }
}
