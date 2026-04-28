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

export interface MarketFundFlowItem {
  name: string
  net_inflow: number
  rank: number
}

export interface MarketRegionFundFlowItem extends MarketFundFlowItem {
  longitude: number | null
  latitude: number | null
}

export interface MarketFundFlow {
  source: string
  regions: MarketRegionFundFlowItem[]
  concept_top: MarketFundFlowItem[]
  concept_bottom: MarketFundFlowItem[]
  industry_top: MarketFundFlowItem[]
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
  fund_flow: MarketFundFlow | null
}
