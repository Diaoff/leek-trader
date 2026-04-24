export interface MarketQuoteItem {
  symbol: string
  code: string
  name: string
  price: number | null
  change_percent: number | null
  volume: number
  sector?: string | null
}

export interface MarketLimitStats {
  total: number
  sample: MarketQuoteItem[]
  source: string
}

export interface NorthboundSummary {
  net_inflow: number | null
  unit: string
  source: string
}

export interface MarketSentiment {
  label: 'strong' | 'range' | 'weak'
  title: string
  score: number
  selection_mode: 'momentum' | 'balanced' | 'defensive'
  advancing_count: number
  declining_count: number
  flat_count: number
  limit_up_count: number
  limit_down_count: number
  northbound_net_inflow: number | null
  summary: string
}

export interface MarketBreadthBucket {
  key: string
  label: string
  count: number
  tone: 'rise' | 'fall'
}

export interface MarketBreadthDistribution {
  advancing_count: number
  flat_count: number
  declining_count: number
  buckets: MarketBreadthBucket[]
  source: string
}

export interface MarketTurnoverSummary {
  today_amount: number | null
  previous_day_amount: number | null
  delta_amount: number | null
  estimated_full_day_amount: number | null
  unit: string
  source: string
}

export interface SectorMomentum {
  sector: string
  rank: number
  avg_change_pct: number
  positive_ratio: number
  candidate_count: number
  leading_symbol: string | null
  leading_name: string | null
  momentum_score: number
}

export interface MarketOverview {
  generated_at: string
  indices: MarketQuoteItem[]
  top_gainers: MarketQuoteItem[]
  top_losers: MarketQuoteItem[]
  limit_up: MarketLimitStats
  limit_down: MarketLimitStats
  northbound: NorthboundSummary
  hot_stocks: MarketQuoteItem[]
  market_sentiment: MarketSentiment | null
  breadth_distribution: MarketBreadthDistribution | null
  turnover_summary: MarketTurnoverSummary | null
  sector_momentum_top: SectorMomentum[]
}

export interface MarketRecommendation {
  symbol: string
  code: string
  name: string
  type: 'stock' | 'etf'
  risk: 'low' | 'medium' | 'high'
  reason: string
  price: number | null
  change_pct: number | null
  source: 'rule_engine' | 'fallback_etf' | 'research_snapshot'
  score: number | null
  strategy: string | null
  layer: 'oversold' | 'support' | 'pullback' | null
  sector: string | null
  sector_rank: number | null
  reasons: string[]
  support_type: string | null
  support_price: number | null
  support_distance_pct: number | null
  atr_stop_loss: number | null
  run_id: number | null
  previous_recommendation_price: number | null
  previous_recommendation_at: string | null
}

export interface MarketResearchRun {
  id: number
  task_id: string | null
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  triggered_by: string
  candidate_pool_size: number
  recommendation_count: number
  northbound_net_inflow: number | null
  summary: string | null
  report_summary: string | null
  error_message: string | null
  generated_at: string | null
  started_at: string
  finished_at: string | null
  market_sentiment: MarketSentiment | null
  sector_momentum_top: SectorMomentum[]
}

export interface MarketResearchLatest {
  snapshot: MarketResearchRun | null
  items: MarketRecommendation[]
  latest_task: MarketResearchRun | null
}

export interface MarketResearchHistory {
  runs: MarketResearchRun[]
}

export interface MarketResearchRunDispatch {
  status: 'queued'
  run_id: number
  task_id: string
}
