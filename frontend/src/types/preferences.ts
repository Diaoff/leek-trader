export interface TradingPreferences {
  commission_rate: number
  min_commission: number
  stamp_tax_rate: number
  stamp_tax_side: 'sell'
  max_daily_trades: number
  single_position_limit_pct: number
  total_exposure_limit_pct: number
  daily_loss_limit_pct: number
}

export interface RiskRuleVersion {
  version: string
  schema_version: number
  threshold_snapshot: Record<string, number>
  change_source: string
  changed_at: string
  description: string
  notes: string[]
}

export interface SmartSelectionPreferences {
  enabled: boolean
  schedule_time: string
  config_payload: Record<string, unknown>
}

export interface StrategySchedulerPreferences {
  enabled: boolean
  interval_seconds: number
  trading_hours_only: boolean
}

export interface Preferences {
  tenant_id: string
  trading: TradingPreferences
  risk_rule_version: RiskRuleVersion
  smart_selection: SmartSelectionPreferences
  strategy_scheduler: StrategySchedulerPreferences
  updated_at: string
}

export interface PreferencesUpdatePayload {
  trading?: Partial<Omit<TradingPreferences, 'stamp_tax_side'>>
  smart_selection?: Partial<Pick<SmartSelectionPreferences, 'enabled' | 'config_payload'>>
  strategy_scheduler?: Partial<StrategySchedulerPreferences>
}
