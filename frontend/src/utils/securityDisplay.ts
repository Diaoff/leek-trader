export interface SecurityDisplaySource {
  symbol: string
  name?: string | null
}

export function formatSecurityDisplay(item: SecurityDisplaySource | string | null | undefined): string {
  if (!item) {
    return '--'
  }
  if (typeof item === 'string') {
    return item
  }
  const symbol = item.symbol || '--'
  const name = item.name?.trim()
  return name ? `${name} · ${symbol}` : symbol
}
