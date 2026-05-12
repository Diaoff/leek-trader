import { defineStore } from 'pinia'

import { fetchAccounts } from '../api/accounts'
import { fetchOrders } from '../api/orders'
import { fetchPortfolioSummary } from '../api/portfolio'
import { fetchPositions } from '../api/positions'
import { fetchMonthlyStats, fetchReportingSummary, fetchTotalAssetCurve } from '../api/reporting'
import { fetchQuotes } from '../api/quotes'
import { fetchWatchlists } from '../api/watchlists'
import { fetchStrategies } from '../api/strategies'
import type { Account } from '../types/account'
import type { PeriodStat, ReportingSummary, TotalAssetCurvePoint } from '../types/reporting'
import type { OrderItem } from '../types/order'
import type { PositionItem } from '../types/position'
import type { PortfolioSummary } from '../types/portfolio'
import type { QuoteItem } from '../types/quote'
import type { StrategyItem } from '../types/strategy'

export const useDashboardStore = defineStore('dashboard', {
  state: () => ({
    accounts: [] as Account[],
    orders: [] as OrderItem[],
    positions: [] as PositionItem[],
    watchlist: [] as Array<QuoteItem & {
      name: string
      code: string
    }>,
    activeStrategies: [] as StrategyItem[],
    summary: {
      total_equity: 0,
      available_cash: 0,
      frozen_cash: 0,
      market_value: 0,
      unrealized_pnl: 0,
    } as PortfolioSummary,
    reporting: {
      trade_count: 0,
      realized_pnl: 0,
      win_rate: 0,
      cumulative_return: 0,
      profit_factor: 0,
      max_drawdown: 0,
      avg_win: 0,
      avg_loss: 0,
      annualized_return_pct: null,
      annualized_volatility_pct: null,
      sharpe_ratio: null,
      calmar_ratio: null,
    } as ReportingSummary,
    equityCurve: [] as TotalAssetCurvePoint[],
    monthlyStats: [] as PeriodStat[],
    loading: false,
    error: '',
    lastUpdated: '未刷新',
  }),

  getters: {
    primaryAccount: (state) => state.accounts[0] ?? null,
    recentOrders: (state) => state.orders.slice(0, 5),
    metricCards: (state) => [
      {
        label: '总资产',
        value: `¥${state.summary.total_equity.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
        hint: `累计收益 ${(state.reporting.cumulative_return * 100).toFixed(2)}%`,
        emphasisClass: '',
      },
      {
        label: '可用资金',
        value: `¥${state.summary.available_cash.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
        hint: `冻结资金 ¥${state.summary.frozen_cash.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
        emphasisClass: '',
      },
      {
        label: '持仓市值',
        value: `¥${state.summary.market_value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
        hint: `当前持仓 ${state.positions.length} 只`,
        emphasisClass: '',
      },
      {
        label: '已实现盈亏',
        value: `¥${state.reporting.realized_pnl.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
        hint: `胜率 ${(state.reporting.win_rate * 100).toFixed(2)}%`,
        emphasisClass: state.reporting.realized_pnl >= 0 ? 'text-emerald-700' : 'text-rose-700',
      },
    ],
  },

  actions: {
    async loadDashboardData() {
      this.loading = true
      this.error = ''

      try {
        const [
          accountsData,
          summaryData,
          reportingData,
          curveData,
          monthlyData,
          ordersData,
          positionsData,
          watchlistsData,
          strategiesData,
        ] = await Promise.all([
          fetchAccounts(),
          fetchPortfolioSummary(),
          fetchReportingSummary(),
          fetchTotalAssetCurve(),
          fetchMonthlyStats(),
          fetchOrders(),
          fetchPositions(),
          fetchWatchlists(),
          fetchStrategies(),
        ])

        this.accounts = accountsData
        this.summary = summaryData
        this.reporting = reportingData
        this.orders = ordersData
        this.positions = positionsData
        this.monthlyStats = monthlyData
        this.equityCurve = curveData.length > 0
          ? curveData
          : [{ label: '当前', total_equity: summaryData.total_equity }]

        // Load watchlist quotes
        if (watchlistsData.length > 0) {
          const symbols = watchlistsData.map((item) => item.symbol)
          const watchlistMap = new Map(watchlistsData.map((item) => [item.symbol, item]))
          const quotes = await fetchQuotes(symbols)
          this.watchlist = quotes.map((quote) => ({
            ...quote,
            name: watchlistMap.get(quote.symbol)?.security_name ?? quote.symbol,
            code: watchlistMap.get(quote.symbol)?.security_code ?? quote.symbol,
          }))
        } else {
          this.watchlist = []
        }

        this.activeStrategies = strategiesData.filter((strategy) => strategy.status === 'active')

        this.lastUpdated = new Date().toLocaleString('zh-CN', {
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false,
        })
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : '仪表盘数据加载失败'
        throw error
      } finally {
        this.loading = false
      }
    },
  },
})
