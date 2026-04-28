const MARKET_TIME_ZONE = "Asia/Shanghai"
const TRADING_WINDOWS: Array<[number, number, number, number]> = [
  [9, 30, 11, 30],
  [13, 0, 15, 0],
]

export function isTradingTime(value = new Date()): boolean {
  const marketDate = toMarketDateParts(value)
  if (marketDate.weekday === 6 || marketDate.weekday === 7) {
    return false
  }

  const minuteOfDay = marketDate.hour * 60 + marketDate.minute
  return TRADING_WINDOWS.some(([startHour, startMinute, endHour, endMinute]) => {
    const start = startHour * 60 + startMinute
    const end = endHour * 60 + endMinute
    return minuteOfDay >= start && minuteOfDay <= end
  })
}

function toMarketDateParts(value: Date): { weekday: number; hour: number; minute: number } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: MARKET_TIME_ZONE,
    weekday: "short",
    hour: "numeric",
    minute: "numeric",
    hour12: false,
  }).formatToParts(value)

  const byType = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return {
    weekday: weekdayNumber(byType.weekday),
    hour: Number(byType.hour),
    minute: Number(byType.minute),
  }
}

function weekdayNumber(value: string): number {
  const weekdays: Record<string, number> = {
    Mon: 1,
    Tue: 2,
    Wed: 3,
    Thu: 4,
    Fri: 5,
    Sat: 6,
    Sun: 7,
  }
  return weekdays[value] ?? 7
}
