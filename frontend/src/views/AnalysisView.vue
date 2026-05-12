<template>
  <section class="space-y-6">
    <div class="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
      <PageHeader
        title="盈亏复盘"
        subtitle="用权益轨迹、月度盈亏和关键风险指标回看当前模拟交易系统的运行表现。"
      />
      <div class="flex flex-wrap gap-2">
        <button class="secondary-button" type="button" :disabled="exportingCsv" @click="exportTradesCsv">
          {{ exportingCsv ? '导出中...' : '导出交易 CSV' }}
        </button>
        <button class="secondary-button" type="button" :disabled="loading" @click="loadAnalysisData">
          刷新复盘
        </button>
      </div>
    </div>

    <ErrorAlert :message="error" type="error" />

    <div class="panel space-y-5">
      <div class="panel-header !mb-0">
        <div>
          <div class="section-label">Backtest MVP</div>
          <h3 class="panel-title mt-3">轻量事件驱动回测</h3>
          <p class="panel-subtitle">复用现有策略插件和历史日线，按逐日事件最小闭环回放信号与交易。</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <button class="secondary-button" type="button" :disabled="backtestLoading" @click="runQuickBacktest">
            {{ backtestLoading ? '回测中...' : '运行回测' }}
          </button>
          <button class="primary-button" type="button" :disabled="backtestLoading" @click="runDailyReview">
            生成收盘复盘
          </button>
        </div>
      </div>

      <div class="grid gap-4 lg:grid-cols-4">
        <div>
          <label class="field-label" for="backtest-symbol">标的</label>
          <input id="backtest-symbol" v-model.trim="backtestForm.symbol" class="field-input" type="text" placeholder="sh600519" />
        </div>
        <div>
          <label class="field-label" for="backtest-configured-strategy">已配置策略</label>
          <select id="backtest-configured-strategy" v-model.number="backtestForm.strategy_id" class="field-select" @change="syncBacktestStrategyType">
            <option :value="0">不使用配置</option>
            <option v-for="strategy in configuredStrategies" :key="strategy.id" :value="strategy.id">
              {{ strategy.name }} · {{ displayStrategy(strategy.strategy_type) }}
            </option>
          </select>
        </div>
        <div>
          <label class="field-label" for="backtest-strategy">策略</label>
          <select id="backtest-strategy" v-model="backtestForm.strategy_type" class="field-select" :disabled="backtestForm.strategy_id > 0">
            <option value="moving_average">双均线</option>
            <option value="macd">MACD</option>
            <option value="rl_trading">RL 实验</option>
          </select>
        </div>
        <div>
          <label class="field-label" for="backtest-start">开始日期</label>
          <input id="backtest-start" v-model="backtestForm.start_date" class="field-input" type="date" />
        </div>
        <div>
          <label class="field-label" for="backtest-end">结束日期</label>
          <input id="backtest-end" v-model="backtestForm.end_date" class="field-input" type="date" />
        </div>
      </div>

      <div class="flex flex-wrap gap-3 text-sm text-[var(--text-secondary)]">
        <label class="inline-flex items-center gap-2"><input v-model="backtestForm.use_example_parameters" type="checkbox" :disabled="backtestForm.strategy_id > 0" /> 载入示例参数</label>
        <label class="inline-flex items-center gap-2"><input v-model="backtestForm.max_position_enabled" type="checkbox" /> 限制最大仓位</label>
        <span v-if="selectedBacktestStrategy" class="status-chip subtle">使用 {{ selectedBacktestStrategy.name }} 的实际参数</span>
      </div>

      <div v-if="backtestJob" class="rounded-[20px] border border-white/5 bg-white/[0.03] p-4">
        <div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div class="section-label">Backtest Job</div>
            <h3 class="panel-title mt-2">{{ backtestJob.progress_label || statusText(backtestJob.status) }}</h3>
            <p class="panel-subtitle mt-2">任务：{{ backtestJob.job_id }} · 状态：{{ statusText(backtestJob.status) }}</p>
          </div>
          <span :class="['status-chip', backtestJob.status === 'succeeded' ? 'positive' : backtestJob.status === 'failed' ? 'negative' : 'neutral']">{{ Math.round(backtestJob.progress_pct) }}%</span>
        </div>
        <div class="mt-4 h-2 overflow-hidden rounded-full bg-white/10">
          <div class="h-full rounded-full bg-[var(--accent-primary)] transition-all" :style="{ width: `${Math.min(Math.max(backtestJob.progress_pct, 0), 100)}%` }"></div>
        </div>
        <ul v-if="backtestJob.progress_details.length" class="mt-3 space-y-1 text-sm text-[var(--text-secondary)]">
          <li v-for="detail in backtestJob.progress_details" :key="detail">{{ detail }}</li>
        </ul>
      </div>

      <div v-if="backtestResult" class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="最终净值" :value="formatCurrency(backtestResult.final_net_worth)" :hint="`收益率 ${formatPercent(backtestResult.total_return_pct / 100)}`" :emphasis-class="backtestResult.total_return_pct >= 0 ? 'value-rise' : 'value-fall'" />
        <MetricCard label="最大回撤" :value="formatPercent(backtestResult.max_drawdown_pct / 100)" hint="事件驱动回放的风险峰谷" :emphasis-class="backtestResult.max_drawdown_pct <= 10 ? 'value-positive' : 'value-negative'" />
        <MetricCard label="交易笔数" :value="String(backtestResult.trade_count)" :hint="`样本 ${backtestResult.bars} 根`" emphasis-class="" />
        <MetricCard label="夏普比率" :value="formatReportNumber('sharpe_ratio')" :hint="`年化 ${formatPercent(reportMetric('annualized_return_pct') / 100)}`" emphasis-class="" />
      </div>

      <div v-if="backtestResult" class="grid gap-3 md:grid-cols-3">
        <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
          <div class="muted-text text-sm">Sortino / Calmar</div>
          <div class="mt-2 mono-data">{{ formatReportNumber('sortino_ratio') }} / {{ formatReportNumber('calmar_ratio') }}</div>
        </div>
        <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
          <div class="muted-text text-sm">胜率 / 买卖次数</div>
          <div class="mt-2 mono-data">{{ formatPercent(reportMetric('win_rate_pct') / 100) }} · {{ reportMetric('buy_count') }} / {{ reportMetric('sell_count') }}</div>
        </div>
        <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
          <div class="muted-text text-sm">费用 / 策略</div>
          <div class="mt-2 mono-data">{{ formatCurrency(reportMetric('total_fees')) }} · {{ displayBacktestStrategy(backtestResult) }}</div>
        </div>
      </div>

      <div v-if="backtestDiagnostics" class="rounded-[20px] border border-white/5 bg-white/[0.03] p-4">
        <div class="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div>
            <div class="section-label">Backtest Diagnostics</div>
            <h3 class="panel-title mt-2">{{ backtestDiagnostics.zero_trade ? '零交易诊断' : '信号诊断' }}</h3>
            <p class="panel-subtitle mt-2">统计信号、RL 模型动作和未成交原因，帮助判断是策略太严还是模型一直观望。</p>
          </div>
          <span :class="['status-chip', backtestDiagnostics.zero_trade ? 'negative' : 'positive']">
            {{ backtestDiagnostics.zero_trade ? '交易为 0' : '已有成交' }}
          </span>
        </div>
        <div class="mt-4 grid gap-3 md:grid-cols-3">
          <div class="rounded-[16px] border border-white/5 bg-black/10 p-3">
            <div class="muted-text text-sm">信号分布</div>
            <div class="mt-2 text-sm text-[var(--text-secondary)]">{{ formatCountMap(backtestDiagnostics.signal_counts) }}</div>
          </div>
          <div class="rounded-[16px] border border-white/5 bg-black/10 p-3">
            <div class="muted-text text-sm">RL 动作分布</div>
            <div class="mt-2 text-sm text-[var(--text-secondary)]">{{ formatCountMap(backtestDiagnostics.rl_action_counts) }}</div>
          </div>
          <div class="rounded-[16px] border border-white/5 bg-black/10 p-3">
            <div class="muted-text text-sm">未成交原因</div>
            <div class="mt-2 text-sm text-[var(--text-secondary)]">{{ formatCountMap(backtestDiagnostics.no_trade_reason_counts) }}</div>
          </div>
        </div>
        <div v-if="backtestNoTradeSamples.length" class="mt-4 table-shell">
          <table class="data-table">
            <thead>
              <tr>
                <th>日期</th>
                <th>信号</th>
                <th>模型动作</th>
                <th>目标仓位</th>
                <th>原因</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="sample in backtestNoTradeSamples" :key="String(sample.trade_date) + String(sample.reason)">
                <td class="mono-data">{{ sample.trade_date }}</td>
                <td>{{ sample.signal }}</td>
                <td>{{ sample.rl_action_type ?? '--' }}</td>
                <td class="mono-data">{{ formatPercent(Number(sample.target_position_pct ?? 0)) }}</td>
                <td>{{ noTradeReasonLabel(String(sample.reason ?? '')) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="dailyReview" class="rounded-[20px] border border-white/5 bg-white/[0.03] p-4">
        <div class="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div>
            <div class="section-label">Daily Review</div>
            <h3 class="panel-title mt-2">{{ dailyReview.headline }}</h3>
            <p class="panel-subtitle mt-2">复盘日期：{{ dailyReview.review_date ?? '--' }}</p>
          </div>
          <span :class="['status-chip', dailyReview.status === 'completed' ? 'positive' : 'neutral']">{{ dailyReview.status }}</span>
        </div>
        <div class="mt-4 grid gap-4 md:grid-cols-3">
          <div>
            <div class="muted-text text-sm">亮点</div>
            <ul class="mt-2 space-y-2 text-sm text-[var(--text-secondary)]">
              <li v-for="item in dailyReview.highlights" :key="item">{{ item }}</li>
            </ul>
          </div>
          <div>
            <div class="muted-text text-sm">风险</div>
            <ul class="mt-2 space-y-2 text-sm text-[var(--text-secondary)]">
              <li v-for="item in dailyReview.risks" :key="item">{{ item }}</li>
            </ul>
          </div>
          <div>
            <div class="muted-text text-sm">下一步</div>
            <ul class="mt-2 space-y-2 text-sm text-[var(--text-secondary)]">
              <li v-for="item in dailyReview.next_actions" :key="item">{{ item }}</li>
            </ul>
          </div>
        </div>
      </div>

      <div class="rounded-[20px] border border-white/5 bg-white/[0.03] p-4">
        <div class="flex items-center justify-between gap-3">
          <div>
            <div class="section-label">Review Archive</div>
            <h3 class="panel-title mt-2">历史复盘</h3>
            <p class="panel-subtitle mt-2">生成收盘复盘后会本地归档，刷新页面仍可查询。</p>
          </div>
          <button class="secondary-button" type="button" @click="loadDailyReviews">刷新归档</button>
        </div>
        <div v-if="dailyReviews.length === 0" class="compact-empty mt-4">暂无历史复盘</div>
        <div v-else class="mt-4 grid gap-3 md:grid-cols-2">
          <div v-for="review in dailyReviews.slice(0, 6)" :key="review.id" class="rounded-[16px] border border-white/5 bg-black/10 p-3 text-sm">
            <div class="flex items-start justify-between gap-3">
              <div class="font-semibold">{{ review.headline }}</div>
              <span class="status-chip subtle">{{ review.review_date ?? '--' }}</span>
            </div>
            <div class="mt-2 text-xs text-[var(--text-secondary)]">{{ review.symbol }} · {{ review.strategy_name || displayStrategy(review.strategy_type) }}</div>
            <div class="mt-2 text-xs text-[var(--text-secondary)]">收益 {{ review.backtest_summary.total_return_pct ?? '--' }}% / 回撤 {{ review.backtest_summary.max_drawdown_pct ?? '--' }}% / 交易 {{ review.backtest_summary.trade_count ?? '--' }}</div>
          </div>
        </div>
      </div>

      <div v-if="backtestResult" class="table-shell">
        <table class="data-table">
          <thead>
            <tr>
              <th>日期</th>
              <th>事件</th>
              <th>净值</th>
              <th>仓位</th>
              <th>回撤</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in backtestResult.equity_curve.slice(-5)" :key="String(row.trade_date)">
              <td class="mono-data">{{ row.trade_date }}</td>
              <td>{{ row.signal }}</td>
              <td class="mono-data">{{ formatCurrency(Number(row.net_worth ?? 0)) }}</td>
              <td class="mono-data">{{ formatPercent(Number(row.position_pct ?? 0)) }}</td>
              <td class="mono-data">{{ formatPercent(Number(row.drawdown_pct ?? 0) / 100) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <MetricCard
        label="累计收益"
        :value="formatCurrency(summary.realized_pnl)"
        :hint="`累计收益率 ${formatPercent(summary.cumulative_return)}`"
        :emphasis-class="summary.realized_pnl >= 0 ? 'value-rise' : 'value-fall'"
      />
      <MetricCard
        label="交易胜率"
        :value="formatPercent(summary.win_rate)"
        :hint="`累计成交 ${summary.trade_count} 笔`"
        :emphasis-class="summary.win_rate >= 0.5 ? 'value-positive' : 'value-warning'"
      />
      <MetricCard
        label="盈利因子"
        :value="summary.profit_factor.toFixed(2)"
        :hint="`平均盈利 ${formatCurrency(summary.avg_win)}`"
        emphasis-class=""
      />
      <MetricCard
        label="最大回撤"
        :value="formatPercent(summary.max_drawdown)"
        :hint="`平均亏损 ${formatCurrency(summary.avg_loss)}`"
        :emphasis-class="summary.max_drawdown <= 0.1 ? 'value-positive' : 'value-negative'"
      />
    </div>

    <div class="grid gap-4 2xl:grid-cols-2">
      <ChartCard
        ref="equityChartRef"
        title="权益轨迹"
        :loading="loading"
        height="h-80"
      />
      <ChartCard
        ref="monthlyChartRef"
        title="月度实现盈亏"
        :loading="loading"
        height="h-80"
      />
    </div>

    <div class="grid gap-4 2xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
      <div class="panel">
        <div class="panel-header">
          <div>
            <h3 class="panel-title">月度表现拆解</h3>
            <p class="panel-subtitle">按月份追踪交易笔数、当月盈亏和期末权益。</p>
          </div>
        </div>

        <div v-if="monthlyStats.length === 0" class="empty-state">
          <div>暂无月度统计</div>
          <div class="text-sm text-[var(--text-tertiary)]">等待后端生成 reporting 数据。</div>
        </div>
        <div v-else class="table-shell">
          <table class="data-table">
            <thead>
              <tr>
                <th>期间</th>
                <th>交易笔数</th>
                <th>实现盈亏</th>
                <th>期末权益</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in monthlyStats" :key="row.period">
                <td class="mono-data">{{ row.period }}</td>
                <td class="mono-data">{{ row.trade_count }}</td>
                <td :class="['mono-data font-semibold', row.realized_pnl >= 0 ? 'value-rise' : 'value-fall']">
                  {{ formatCurrency(row.realized_pnl) }}
                </td>
                <td class="mono-data">{{ formatCurrency(row.ending_equity) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="panel space-y-4">
        <div>
          <div class="section-label">Risk Lens</div>
          <h3 class="panel-title mt-3">风险结构</h3>
        </div>

        <div class="rounded-[20px] border border-white/5 bg-white/[0.03] p-4">
          <div class="muted-text text-sm">回撤控制</div>
          <div :class="['mt-2 text-3xl font-semibold tracking-[-0.04em]', summary.max_drawdown <= 0.1 ? 'value-positive' : 'value-negative']">
            {{ formatPercent(summary.max_drawdown) }}
          </div>
          <div class="mt-2 text-sm text-[var(--text-tertiary)]">最大回撤越低，说明资金曲线越平稳。</div>
        </div>

        <div class="rounded-[20px] border border-white/5 bg-white/[0.03] p-4">
          <div class="muted-text text-sm">盈亏结构</div>
          <div class="mt-3 grid grid-cols-2 gap-3 text-sm">
            <div>
              <div class="muted-text">平均盈利</div>
              <div class="mt-1 mono-data value-rise">{{ formatCurrency(summary.avg_win) }}</div>
            </div>
            <div>
              <div class="muted-text">平均亏损</div>
              <div class="mt-1 mono-data value-fall">{{ formatCurrency(summary.avg_loss) }}</div>
            </div>
            <div>
              <div class="muted-text">胜率</div>
              <div class="mt-1 mono-data">{{ formatPercent(summary.win_rate) }}</div>
            </div>
            <div>
              <div class="muted-text">盈利因子</div>
              <div class="mt-1 mono-data">{{ summary.profit_factor.toFixed(2) }}</div>
            </div>
          </div>
        </div>

        <div class="rounded-[20px] border border-white/5 bg-white/[0.03] p-4">
          <div class="muted-text text-sm">年度滚动统计</div>
          <div v-if="yearlyStats.length === 0" class="mt-3 text-sm text-[var(--text-tertiary)]">
            暂无年度数据。
          </div>
          <div v-else class="mt-3 space-y-3">
            <div
              v-for="row in yearlyStats"
              :key="row.period"
              class="flex items-center justify-between rounded-2xl border border-white/5 px-4 py-3"
            >
              <div>
                <div class="font-semibold">{{ row.period }}</div>
                <div class="text-xs text-[var(--text-tertiary)]">{{ row.trade_count }} 笔交易</div>
              </div>
              <div class="text-right">
                <div :class="['mono-data font-semibold', row.realized_pnl >= 0 ? 'value-rise' : 'value-fall']">
                  {{ formatCurrency(row.realized_pnl) }}
                </div>
                <div class="text-xs text-[var(--text-tertiary)]">权益 {{ formatCurrency(row.ending_equity) }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { buildBacktestDailyReview, fetchBacktestJob, fetchDailyReviews, fetchLatestBacktestJob, submitBacktestJob, type BacktestDailyReviewResponse, type BacktestJobResponse, type BacktestRunRequest, type BacktestRunResponse, type DailyReviewArchiveItem } from '../api/backtest'
import { downloadTradesCsv, fetchEquityCurve, fetchMonthlyStats, fetchReportingSummary, fetchYearlyStats } from '../api/reporting'
import { fetchStrategies } from '../api/strategies'
import type { EquityCurvePoint, PeriodStat, ReportingSummary } from '../types/reporting'
import type { StrategyItem } from '../types/strategy'
import ChartCard from '../components/ChartCard.vue'
import ErrorAlert from '../components/ErrorAlert.vue'
import MetricCard from '../components/MetricCard.vue'
import PageHeader from '../components/PageHeader.vue'
import { formatCurrency, formatPercent } from '../utils/format'
import { getApiErrorMessage } from '../utils/http'

interface ChartCardExpose {
  initChart: () => Promise<void>
  setOption: (option: object) => void
}

const loading = ref(false)
const error = ref('')
const summary = ref<ReportingSummary>({
  trade_count: 0,
  realized_pnl: 0,
  win_rate: 0,
  cumulative_return: 0,
  profit_factor: 0,
  max_drawdown: 0,
  avg_win: 0,
  avg_loss: 0,
})
const equityCurve = ref<EquityCurvePoint[]>([])
const monthlyStats = ref<PeriodStat[]>([])
const yearlyStats = ref<PeriodStat[]>([])
const backtestLoading = ref(false)
const backtestResult = ref<BacktestRunResponse | null>(null)
const dailyReview = ref<BacktestDailyReviewResponse | null>(null)
const dailyReviews = ref<DailyReviewArchiveItem[]>([])
const backtestJob = ref<BacktestJobResponse | null>(null)
const configuredStrategies = ref<StrategyItem[]>([])
const exportingCsv = ref(false)
let backtestPollTimer: number | null = null
const defaultBacktestEndDate = formatDateInput(new Date())
const defaultBacktestStartDate = formatDateInput(new Date(new Date().getFullYear() - 1, 0, 1))
const backtestForm = ref({
  symbol: 'sh600519',
  strategy_id: 0,
  strategy_type: 'moving_average' as 'moving_average' | 'macd' | 'rl_trading',
  start_date: defaultBacktestStartDate,
  end_date: defaultBacktestEndDate,
  use_example_parameters: true,
  max_position_enabled: true,
})

const selectedBacktestStrategy = computed(() => configuredStrategies.value.find((strategy) => strategy.id === backtestForm.value.strategy_id) ?? null)
const backtestDiagnostics = computed(() => backtestResult.value?.summary?.diagnostics ?? null)
const backtestNoTradeSamples = computed(() => backtestDiagnostics.value?.no_trade_samples ?? [])

const equityChartRef = ref<ChartCardExpose | null>(null)
const monthlyChartRef = ref<ChartCardExpose | null>(null)

function formatDateInput(value: Date): string {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function buildEquityOption(): object {
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(7, 14, 25, 0.94)',
      borderColor: 'rgba(121, 168, 220, 0.22)',
      textStyle: { color: '#dbe7f5' },
    },
    grid: { left: 14, right: 18, top: 24, bottom: 20, containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: equityCurve.value.map((item) => item.label),
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } },
      axisLabel: { color: '#6f86a4' },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      axisLabel: {
        color: '#6f86a4',
        formatter: (value: number) => `${(value / 10000).toFixed(1)}w`,
      },
    },
    series: [
      {
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 3, color: '#67b7ff' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(103, 183, 255, 0.34)' },
              { offset: 1, color: 'rgba(103, 183, 255, 0.02)' },
            ],
          },
        },
        data: equityCurve.value.map((item) => item.total_equity),
      },
    ],
  }
}

function buildMonthlyOption(): object {
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(7, 14, 25, 0.94)',
      borderColor: 'rgba(121, 168, 220, 0.22)',
      textStyle: { color: '#dbe7f5' },
      valueFormatter: (value: number) => formatCurrency(value),
    },
    grid: { left: 14, right: 18, top: 24, bottom: 20, containLabel: true },
    xAxis: {
      type: 'category',
      data: monthlyStats.value.map((item) => item.period),
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } },
      axisLabel: { color: '#6f86a4' },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      axisLabel: {
        color: '#6f86a4',
        formatter: (value: number) => `${(value / 1000).toFixed(0)}k`,
      },
    },
    series: [
      {
        type: 'line',
        smooth: true,
        symbolSize: 8,
        lineStyle: { width: 3, color: '#3fd0a4' },
        itemStyle: { color: '#3fd0a4' },
        data: monthlyStats.value.map((item) => item.realized_pnl),
      },
    ],
  }
}

async function renderCharts(): Promise<void> {
  await nextTick()

  if (equityChartRef.value) {
    await equityChartRef.value.initChart()
    equityChartRef.value.setOption(buildEquityOption())
  }

  if (monthlyChartRef.value) {
    await monthlyChartRef.value.initChart()
    monthlyChartRef.value.setOption(buildMonthlyOption())
  }
}

async function loadAnalysisData(): Promise<void> {
  loading.value = true
  error.value = ''

  try {
    const [summaryData, curveData, monthlyData, yearlyData] = await Promise.all([
      fetchReportingSummary(),
      fetchEquityCurve(),
      fetchMonthlyStats(),
      fetchYearlyStats(),
    ])
    summary.value = summaryData
    equityCurve.value = curveData
    monthlyStats.value = monthlyData
    yearlyStats.value = yearlyData
    await loadDailyReviews()
    await renderCharts()
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : '复盘数据加载失败'
  } finally {
    loading.value = false
  }
}

async function exportTradesCsv(): Promise<void> {
  exportingCsv.value = true
  try {
    await downloadTradesCsv()
  } finally {
    exportingCsv.value = false
  }
}

async function loadDailyReviews(): Promise<void> {
  const payload = await fetchDailyReviews({ limit: 10 })
  dailyReviews.value = payload.reviews
}

async function loadConfiguredStrategies(): Promise<void> {
  try {
    configuredStrategies.value = await fetchStrategies()
  } catch {
    configuredStrategies.value = []
  }
}

async function runQuickBacktest(): Promise<void> {
  backtestLoading.value = true
  error.value = ''
  dailyReview.value = null
  backtestResult.value = null
  stopBacktestPolling()
  try {
    const job = await submitBacktestJob(buildBacktestPayload())
    backtestJob.value = job
    startBacktestPolling(job.job_id)
  } catch (err: unknown) {
    backtestLoading.value = false
    error.value = getApiErrorMessage(err, '回测任务提交失败')
  }
}

async function runDailyReview(): Promise<void> {
  backtestLoading.value = true
  error.value = ''
  try {
    dailyReview.value = await buildBacktestDailyReview(buildBacktestPayload())
    backtestResult.value = dailyReview.value.backtest
    await loadDailyReviews()
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : '收盘复盘生成失败'
  } finally {
    backtestLoading.value = false
  }
}

function startBacktestPolling(jobId: string): void {
  stopBacktestPolling()
  void refreshBacktestJob(jobId)
  backtestPollTimer = window.setInterval(() => {
    void refreshBacktestJob(jobId)
  }, 1200)
}

function stopBacktestPolling(): void {
  if (backtestPollTimer !== null) {
    window.clearInterval(backtestPollTimer)
    backtestPollTimer = null
  }
}

async function refreshBacktestJob(jobId: string): Promise<void> {
  try {
    const job = await fetchBacktestJob(jobId)
    backtestJob.value = job
    if (job.status === 'succeeded' || job.status === 'failed') {
      stopBacktestPolling()
      backtestLoading.value = false
      if (job.status === 'succeeded' && job.result) {
        backtestResult.value = job.result
      } else if (job.status === 'failed') {
        error.value = job.error || '回测任务失败'
      }
    }
  } catch (err: unknown) {
    stopBacktestPolling()
    backtestLoading.value = false
    const latest = await fetchLatestBacktestJob().catch(() => null)
    if (latest && (latest.status === 'queued' || latest.status === 'running')) {
      backtestJob.value = latest
      startBacktestPolling(latest.job_id)
      return
    }
    error.value = getApiErrorMessage(err, '回测进度刷新失败')
  }
}

function statusText(status: string): string {
  const mapping: Record<string, string> = {
    queued: '排队中',
    running: '运行中',
    succeeded: '已完成',
    failed: '失败',
  }
  return mapping[status] ?? status
}

function buildBacktestPayload(): BacktestRunRequest {
  const payload: BacktestRunRequest = {
    symbol: backtestForm.value.symbol,
    strategy_type: backtestForm.value.strategy_type,
    start_date: backtestForm.value.start_date || null,
    end_date: backtestForm.value.end_date || null,
    initial_cash: 100000,
    commission_rate: 0.0003,
    slippage_rate: 0.0002,
    max_position_pct: backtestForm.value.max_position_enabled ? 0.6 : 1,
    parameters: backtestForm.value.use_example_parameters
      ? {
          short_window: 5,
          long_window: 20,
          position_pct: 0.1,
        }
      : {},
  }
  if (backtestForm.value.strategy_id > 0) {
    payload.strategy_id = backtestForm.value.strategy_id
    payload.strategy_type = (selectedBacktestStrategy.value?.strategy_type as BacktestRunRequest['strategy_type'] | undefined) ?? payload.strategy_type
    payload.parameters = undefined
  }
  return payload
}

function syncBacktestStrategyType(): void {
  if (selectedBacktestStrategy.value) {
    backtestForm.value.strategy_type = selectedBacktestStrategy.value.strategy_type as 'moving_average' | 'macd' | 'rl_trading'
    backtestForm.value.use_example_parameters = false
  }
}

function reportMetric(key: string): number {
  const report = backtestResult.value?.summary?.report as Record<string, unknown> | undefined
  const value = report?.[key]
  return typeof value === 'number' ? value : 0
}

function formatReportNumber(key: string): string {
  return reportMetric(key).toFixed(2)
}

function displayStrategy(value: string): string {
  const mapping: Record<string, string> = {
    moving_average: '双均线',
    macd: 'MACD',
    rl_trading: 'RL 实验',
  }
  return mapping[value] ?? value
}

function displayBacktestStrategy(result: BacktestRunResponse): string {
  return result.strategy_name || displayStrategy(result.strategy_type)
}

function formatCountMap(counts?: Record<string, number>): string {
  if (!counts || Object.keys(counts).length === 0) {
    return '--'
  }
  return Object.entries(counts)
    .map(([key, value]) => `${countLabel(key)} ${value}`)
    .join(' · ')
}

function countLabel(value: string): string {
  const mapping: Record<string, string> = {
    buy: '买入',
    sell: '卖出',
    reduce: '减仓',
    hold: '观望',
  }
  return mapping[value] ?? noTradeReasonLabel(value)
}

function noTradeReasonLabel(value: string): string {
  const mapping: Record<string, string> = {
    min_confidence_not_met: '置信度未达标',
    model_hold_or_zero_target: '模型观望或目标仓位为 0',
    hold_signal: '策略观望',
    zero_target_position: '目标仓位为 0',
    target_delta_too_small: '调仓金额不足一股',
    insufficient_cash_or_lot: '资金或股数不足',
    no_position_to_exit: '无持仓可卖出',
    no_rebalance_needed: '无需调仓',
  }
  return mapping[value] ?? (value || '--')
}

watch(
  () => [equityCurve.value, monthlyStats.value],
  () => {
    void renderCharts()
  },
  { deep: true },
)

onMounted(() => {
  void loadAnalysisData()
  void loadConfiguredStrategies()
})

onBeforeUnmount(() => {
  stopBacktestPolling()
})
</script>
