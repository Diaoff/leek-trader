import type { QuoteItem } from './quotes'

export interface QuoteStreamMessage {
  type: 'subscribed' | 'quotes'
  symbols: string[]
  interval_seconds?: number
  quotes?: QuoteItem[]
}

export function buildQuoteStreamUrl(symbols: string[], intervalSeconds = 5): string {
  const apiBase = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'
  const baseUrl = new URL(apiBase, window.location.origin)
  baseUrl.protocol = baseUrl.protocol === 'https:' ? 'wss:' : 'ws:'
  baseUrl.pathname = `${baseUrl.pathname.replace(/\/$/, '')}/quotes/stream`
  baseUrl.search = ''
  symbols.forEach((symbol) => baseUrl.searchParams.append('symbols', symbol))
  baseUrl.searchParams.set('interval_seconds', String(intervalSeconds))
  return baseUrl.toString()
}

export function openQuoteStream(symbols: string[], onMessage: (message: QuoteStreamMessage) => void, intervalSeconds = 5): WebSocket {
  const socket = new WebSocket(buildQuoteStreamUrl(symbols, intervalSeconds))
  socket.addEventListener('message', (event) => {
    onMessage(JSON.parse(event.data) as QuoteStreamMessage)
  })
  return socket
}
