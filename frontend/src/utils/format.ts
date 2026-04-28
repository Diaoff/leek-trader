export function formatCurrency(value: number | string, currency = 'CNY'): string {
  const amount = typeof value === 'number' ? value : Number(value)
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
  }).format(Number.isFinite(amount) ? amount : 0)
}

export function formatPercent(value: number | string, digits = 2): string {
  const ratio = typeof value === 'number' ? value : Number(value)
  const normalized = Number.isFinite(ratio) ? ratio : 0
  return `${(normalized * 100).toFixed(digits)}%`
}

export function formatDecimal(value: number | string, digits = 2): string {
  const amount = typeof value === 'number' ? value : Number(value)
  return (Number.isFinite(amount) ? amount : 0).toFixed(digits)
}

export function formatDateTime(value: string): string {
  const date = parseApiDateTime(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}

export function parseApiDateTime(value: string): Date {
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`
  return new Date(normalized)
}

export function formatChinaDateTime(value: string | null, fallback = '尚未运行'): string {
  if (!value) {
    return fallback
  }
  const date = parseApiDateTime(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}
