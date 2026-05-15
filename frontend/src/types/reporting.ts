export interface ReportingSummary {
  trade_count: number
  realized_pnl: number
  win_rate: number
  cumulative_return: number
  profit_factor: number
  max_drawdown: number
  avg_win: number
  avg_loss: number
  annualized_return_pct: number | null
  annualized_volatility_pct: number | null
  sharpe_ratio: number | null
  calmar_ratio: number | null
}

export interface TotalAssetCurvePoint {
  label: string
  total_equity: number
}

export type EquityCurvePoint = TotalAssetCurvePoint

export interface PeriodStat {
  period: string
  trade_count: number
  realized_pnl: number
  ending_equity: number
}

export interface ReportingEvent {
  id: number
  tenant_id: string
  user_id: number | null
  account_id: number | null
  event_type: string
  symbol: string | null
  occurred_at: string
  strategy_id: number | null
  strategy_run_id: number | null
  order_id: number | null
  order_event_id: number | null
  trade_id: number | null
  position_id: number | null
  equity_snapshot_id: number | null
  correlation_id: string | null
  risk_rule_version: string | null
  payload: Record<string, unknown>
}
