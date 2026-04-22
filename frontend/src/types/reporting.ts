export interface ReportingSummary {
  trade_count: number
  realized_pnl: number
  win_rate: number
  cumulative_return: number
  profit_factor: number
  max_drawdown: number
  avg_win: number
  avg_loss: number
}

export interface EquityCurvePoint {
  label: string
  total_equity: number
}

export interface PeriodStat {
  period: string
  trade_count: number
  realized_pnl: number
  ending_equity: number
}
