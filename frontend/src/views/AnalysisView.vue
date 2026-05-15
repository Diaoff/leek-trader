<template>
  <section class="space-y-6">
    <div class="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
      <PageHeader title="盈亏复盘" subtitle="支持单标的、组合回测和参数扫描。" />
      <div class="flex flex-wrap gap-2">
        <button class="secondary-button" type="button" :disabled="exportingCsv" @click="exportTradesCsv">{{ exportingCsv ? '导出中...' : '导出交易 CSV' }}</button>
        <button class="secondary-button" type="button" :disabled="loading" @click="loadAnalysisData">刷新复盘</button>
      </div>
    </div>

    <ErrorAlert :message="error" type="error" />

    <div class="panel space-y-5">
      <div class="panel-header !mb-0">
        <div>
          <div class="section-label">Backtest Lab</div>
          <h3 class="panel-title mt-3">单标的 / 组合 / 参数扫描</h3>
          <p class="panel-subtitle">复用现有策略插件和历史日线。</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <button class="secondary-button" type="button" :disabled="busy" @click="runAnalysis">{{ busy ? '执行中...' : actionButtonText }}</button>
          <button v-if="mode === 'optimization'" class="primary-button" type="button" :disabled="busy" @click="loadLatestJob">查看最新扫描</button>
        </div>
      </div>

      <div class="flex flex-wrap gap-2">
        <button v-for="item in modeOptions" :key="item.value" :class="['status-chip', mode === item.value ? 'positive' : 'subtle']" type="button" @click="mode = item.value">{{ item.label }}</button>
      </div>

      <div v-if="mode === 'single' && activeTemplatePreset" class="rounded-[20px] border border-sky-300/15 bg-sky-300/[0.06] p-4">
        <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div class="section-label">模板预设摘要</div>
            <h3 class="panel-title mt-2">{{ activeTemplatePreset.templateName }}</h3>
            <p class="panel-subtitle mt-2">策略类型：{{ displayStrategy(activeTemplatePreset.strategyType) }}</p>
          </div>
          <div class="flex flex-wrap gap-2">
            <span class="status-chip subtle">来源：策略模板</span>
            <RouterLink v-if="templateContextQuery" class="secondary-button" :to="{ name: 'ai', query: templateContextQuery }">
              带模板参数去 AI 建议
            </RouterLink>
          </div>
        </div>
        <div class="mt-4 rounded-[16px] border border-white/5 bg-black/10 p-3 text-sm text-[var(--text-secondary)]">
          {{ formatObject(activeTemplatePreset.parameters) }}
        </div>
        <div class="mt-3 text-sm text-[var(--text-tertiary)]">这是模板研究预设，用于帮助你快速开始模拟回测，不代表收益承诺。</div>
      </div>

      <div class="grid gap-4 lg:grid-cols-4">
        <template v-if="mode === 'single' || mode === 'optimization'">
          <div>
            <label class="field-label" for="symbol">标的</label>
            <input id="symbol" v-model.trim="backtestForm.symbol" class="field-input" type="text" placeholder="sh600519" />
          </div>
          <div>
            <label class="field-label" for="strategy-id">已配置策略</label>
            <select id="strategy-id" v-model.number="backtestForm.strategy_id" class="field-select" @change="syncBacktestStrategyType">
              <option :value="0">不使用配置</option>
              <option v-for="strategy in configuredStrategies" :key="strategy.id" :value="strategy.id">{{ strategy.name }} · {{ displayStrategy(strategy.strategy_type) }}</option>
            </select>
          </div>
          <div>
            <label class="field-label" for="strategy-type">策略</label>
            <select id="strategy-type" v-model="backtestForm.strategy_type" class="field-select" :disabled="backtestForm.strategy_id > 0">
              <option value="moving_average">双均线</option>
              <option value="macd">MACD</option>
              <option value="rl_trading">RL 实验</option>
              <option value="rsi_reversal">RSI</option>
              <option value="bollinger_band">布林带</option>
              <option value="kdj_momentum">KDJ</option>
              <option value="signal_fusion">多信号融合</option>
            </select>
          </div>
        </template>

        <template v-if="mode === 'portfolio'">
          <div class="lg:col-span-2">
            <label class="field-label" for="portfolio-symbols">组合标的</label>
            <input id="portfolio-symbols" v-model.trim="portfolioForm.symbols" class="field-input" type="text" placeholder="sh600519, sz000001" />
          </div>
          <div class="lg:col-span-2">
            <label class="field-label" for="portfolio-weights">组合权重</label>
            <input id="portfolio-weights" v-model.trim="portfolioForm.weights" class="field-input" type="text" placeholder="0.5, 0.5（留空则等权）" />
          </div>
        </template>

        <template v-if="mode === 'optimization'">
          <div>
            <label class="field-label" for="grid-target">目标指标</label>
            <select id="grid-target" v-model="optimizationForm.target_metric" class="field-select">
              <option value="total_return_pct">累计收益</option>
              <option value="max_drawdown_pct">最大回撤</option>
              <option value="sharpe_ratio">夏普比率</option>
              <option value="final_net_worth">最终净值</option>
            </select>
          </div>
          <div>
            <label class="field-label" for="grid-direction">排序方向</label>
            <select id="grid-direction" v-model="optimizationForm.sort_direction" class="field-select">
              <option value="desc">降序</option>
              <option value="asc">升序</option>
            </select>
          </div>
          <div class="lg:col-span-2">
            <label class="field-label" for="grid-text">参数网格</label>
            <input id="grid-text" v-model.trim="optimizationForm.gridText" class="field-input" type="text" placeholder="short_window=3|5, position_pct=0.1|0.2" />
          </div>
        </template>

        <div>
          <label class="field-label" for="start-date">开始日期</label>
          <input id="start-date" v-model="currentStartDate" class="field-input" type="date" />
        </div>
        <div>
          <label class="field-label" for="end-date">结束日期</label>
          <input id="end-date" v-model="currentEndDate" class="field-input" type="date" />
        </div>
      </div>

      <div v-if="mode === 'single'" class="flex flex-wrap gap-3 text-sm text-[var(--text-secondary)]">
        <label class="inline-flex items-center gap-2"><input v-model="backtestForm.use_example_parameters" type="checkbox" :disabled="backtestForm.strategy_id > 0 || hasTemplateParameters" /> 载入示例参数</label>
        <label class="inline-flex items-center gap-2"><input v-model="backtestForm.max_position_enabled" type="checkbox" /> 限制最大仓位</label>
      </div>
      <div v-else class="text-sm text-[var(--text-secondary)]">
        <span v-if="mode === 'portfolio'">组合模式留空权重则自动等权。</span>
        <span v-else>参数扫描限制在 30 组以内。</span>
      </div>

      <div v-if="activeJob" class="rounded-[20px] border border-white/5 bg-white/[0.03] p-4">
        <div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div class="section-label">Backtest Job</div>
            <h3 class="panel-title mt-2">{{ activeJob.progress_label || statusText(activeJob.status) }}</h3>
            <p class="panel-subtitle mt-2">任务：{{ activeJob.job_id }} · 状态：{{ statusText(activeJob.status) }}</p>
            <RouterLink class="mt-3 inline-flex text-sm text-[var(--accent-primary)] hover:underline" :to="{ name: 'backtest-result', params: { jobId: activeJob.job_id }, query: templateContextQuery ?? undefined }">查看独立回测报告 →</RouterLink>
          </div>
          <span :class="['status-chip', activeJob.status === 'succeeded' ? 'positive' : activeJob.status === 'failed' ? 'negative' : 'neutral']">{{ Math.round(activeJob.progress_pct) }}%</span>
        </div>
        <div class="mt-4 h-2 overflow-hidden rounded-full bg-white/10"><div class="h-full rounded-full bg-[var(--accent-primary)] transition-all" :style="{ width: `${Math.min(Math.max(activeJob.progress_pct, 0), 100)}%` }"></div></div>
        <ul v-if="activeJob.progress_details.length" class="mt-3 space-y-1 text-sm text-[var(--text-secondary)]"><li v-for="detail in activeJob.progress_details" :key="detail">{{ detail }}</li></ul>
      </div>

      <div v-if="mode === 'single' && backtestResult" class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="最终净值" :value="formatCurrency(backtestResult.final_net_worth)" :hint="`收益率 ${formatPercent(backtestResult.total_return_pct / 100)}`" :emphasis-class="backtestResult.total_return_pct >= 0 ? 'value-rise' : 'value-fall'" />
        <MetricCard label="最大回撤" :value="formatPercent(backtestResult.max_drawdown_pct / 100)" hint="风控压力" />
        <MetricCard label="交易次数" :value="String(backtestResult.trade_count)" hint="执行交易数" />
        <MetricCard label="样本长度" :value="String(backtestResult.bars)" hint="历史日线根数" />
      </div>

      <div v-if="mode === 'portfolio' && portfolioResult" class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="组合最终净值" :value="formatCurrency(portfolioResult.final_net_worth)" :hint="`收益率 ${formatPercent(portfolioResult.total_return_pct / 100)}`" :emphasis-class="portfolioResult.total_return_pct >= 0 ? 'value-rise' : 'value-fall'" />
        <MetricCard label="组合最大回撤" :value="formatPercent(portfolioResult.max_drawdown_pct / 100)" hint="组合级风险" />
        <MetricCard label="组合交易次数" :value="String(portfolioResult.trade_count)" hint="子回测交易汇总" />
        <MetricCard label="标的数量" :value="String(portfolioResult.symbols.length)" hint="组合成员数" />
      </div>

      <div v-if="mode === 'optimization' && optimizationResult" class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="最佳指标" :value="formatOptimizationMetric(optimizationResult.best_candidate?.metric_value)" :hint="optimizationResult.target_metric" />
        <MetricCard label="组合数量" :value="String(optimizationResult.combinations)" hint="扫描网格数量" />
        <MetricCard label="最佳交易数" :value="String(optimizationResult.best_candidate?.trade_count ?? 0)" hint="最佳候选交易次数" />
        <MetricCard label="样本长度" :value="String(optimizationResult.bars)" hint="历史日线根数" />
      </div>

      <div v-if="mode === 'single' && backtestResult" class="grid gap-4 lg:grid-cols-[2fr,1fr]">
        <ChartCard ref="equityChartRef" title="权益曲线" class="min-h-[360px]" />
        <div class="panel-secondary space-y-3">
          <div class="section-label">最近交易</div>
          <div v-if="backtestResult.trades.length === 0" class="text-sm text-[var(--text-tertiary)]">暂无交易记录。</div>
          <div v-else class="space-y-2"><div v-for="trade in backtestResult.trades.slice(-8)" :key="`${trade.trade_date}-${trade.side}-${trade.execution_price}`" class="rounded-2xl border border-white/5 px-3 py-2 text-sm"><div class="font-medium">{{ trade.trade_date }} · {{ trade.side }}</div><div class="text-[var(--text-tertiary)]">{{ trade.shares_delta }} 股 · {{ formatCurrency(Number(trade.execution_price ?? 0)) }}</div></div></div>
        </div>
      </div>

      <div v-if="mode === 'portfolio' && portfolioResult" class="grid gap-4 lg:grid-cols-[2fr,1fr]">
        <ChartCard ref="equityChartRef" title="组合权益曲线" class="min-h-[360px]" />
        <div class="panel-secondary space-y-3">
          <div class="section-label">组合权重</div>
          <div class="text-sm text-[var(--text-secondary)]">{{ formatObject(portfolioSummaryWeightMap) }}</div>
          <div class="section-label pt-2">组合贡献</div>
          <div v-if="portfolioContributions.length" class="space-y-2 text-sm text-[var(--text-secondary)]">
            <div v-for="item in portfolioContributions" :key="item.symbol">{{ item.symbol }} · {{ formatCurrency(item.pnl) }} · {{ formatPercent((item.total_return_pct ?? 0) / 100) }}</div>
          </div>
        </div>
      </div>

      <div v-if="mode === 'optimization' && optimizationResult" class="grid gap-4 lg:grid-cols-[2fr,1fr]">
        <ChartCard ref="equityChartRef" title="最佳候选权益曲线" class="min-h-[360px]" />
        <div class="panel-secondary space-y-3">
          <div class="section-label">最佳候选</div>
          <div class="text-sm text-[var(--text-secondary)]">{{ formatObject(optimizationResult.best_candidate?.merged_parameters || null) }}</div>
          <div class="section-label pt-2">历史记录</div>
          <div v-if="optimizationHistory.length === 0" class="text-sm text-[var(--text-tertiary)]">暂无扫描历史。</div>
          <div v-else class="space-y-2"><div v-for="item in optimizationHistory" :key="item.job_id" class="rounded-2xl border border-white/5 px-3 py-2 text-sm"><div class="font-medium">{{ item.symbol }} · {{ item.strategy_type }}</div><div class="text-[var(--text-tertiary)]">{{ formatObject(item.best_parameters) }}</div></div></div>
        </div>
      </div>

      <div v-if="mode === 'optimization' && optimizationResult?.candidates?.length" class="rounded-[20px] border border-white/5 bg-white/[0.03] p-4">
        <div class="section-label">扫描结果</div>
        <div class="mt-4 overflow-x-auto">
          <table class="min-w-full text-left text-sm">
            <thead class="text-[var(--text-tertiary)]"><tr><th class="py-2 pr-4">排名</th><th class="py-2 pr-4">参数</th><th class="py-2 pr-4">指标值</th><th class="py-2 pr-4">交易</th></tr></thead>
            <tbody>
              <tr v-for="candidate in optimizationResult.candidates" :key="candidate.rank" class="border-t border-white/5"><td class="py-2 pr-4">{{ candidate.rank }}</td><td class="py-2 pr-4">{{ formatObject(candidate.parameters) }}</td><td class="py-2 pr-4">{{ formatOptimizationMetric(candidate.metric_value) }}</td><td class="py-2 pr-4">{{ candidate.trade_count }}</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="rounded-[20px] border border-white/5 bg-white/[0.03] p-4">
        <div class="panel-header !mb-0">
          <div>
            <div class="section-label">Event Chain</div>
            <h3 class="panel-title mt-2">策略信号到权益快照的因果链</h3>
            <p class="panel-subtitle mt-2">{{ eventChainSummary.subtitle }}</p>
          </div>
          <div class="flex flex-wrap gap-2">
            <span class="status-chip subtle">{{ eventChainSummary.eventCount }} 个事件</span>
            <RouterLink v-if="eventChainAiQuery" class="secondary-button" :to="{ name: 'ai', query: eventChainAiQuery }">
              带事件链去 AI 建议
            </RouterLink>
          </div>
        </div>

        <div v-if="reportingEventsLoading" class="empty-state !min-h-[180px]">
          <div>正在加载事件链...</div>
          <div class="text-sm text-[var(--text-tertiary)]">会按 correlation_id / order_id / strategy_run_id 聚合最近链路。</div>
        </div>
        <div v-else-if="reportingEventsError" class="empty-state !min-h-[180px]">
          <div>事件链暂时不可用</div>
          <div class="text-sm text-[var(--text-tertiary)]">{{ reportingEventsError }}</div>
        </div>
        <div v-else-if="activeEventChain" class="mt-4 space-y-4">
          <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <div class="rounded-[18px] border border-white/5 bg-black/10 px-4 py-3">
              <div class="text-xs text-[var(--text-tertiary)]">链路主键</div>
              <div class="mt-2 text-sm text-[var(--text-secondary)]">{{ eventChainSummary.title }}</div>
            </div>
            <div class="rounded-[18px] border border-white/5 bg-black/10 px-4 py-3">
              <div class="text-xs text-[var(--text-tertiary)]">风控决策</div>
              <div class="mt-2 text-sm text-[var(--text-secondary)]">{{ eventChainSummary.riskDecision ?? '--' }}</div>
            </div>
            <div class="rounded-[18px] border border-white/5 bg-black/10 px-4 py-3">
              <div class="text-xs text-[var(--text-tertiary)]">订单状态</div>
              <div class="mt-2 text-sm text-[var(--text-secondary)]">{{ eventChainSummary.orderStatus ?? '--' }}</div>
            </div>
            <div class="rounded-[18px] border border-white/5 bg-black/10 px-4 py-3">
              <div class="text-xs text-[var(--text-tertiary)]">成交 / 持仓 / 快照</div>
              <div class="mt-2 text-sm text-[var(--text-secondary)]">{{ eventChainSummary.tradeCount }} / {{ eventChainSummary.positionCount }} / {{ eventChainSummary.snapshotCount }}</div>
            </div>
          </div>

          <div v-if="eventChainSummary.fallbackReason" class="rounded-[18px] border border-amber-300/20 bg-amber-300/[0.06] px-4 py-3 text-sm text-[var(--text-secondary)]">
            降级原因：{{ eventChainSummary.fallbackReason }}
          </div>

          <div class="space-y-3">
            <article v-for="event in activeEventChain.events" :key="event.id" class="rounded-[18px] border border-white/5 bg-black/10 px-4 py-4">
              <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div class="min-w-0">
                  <div class="section-label">{{ eventTypeLabel(event.event_type) }}</div>
                  <div class="mt-2 text-sm text-[var(--text-secondary)]">{{ summarizeReportingEvent(event) }}</div>
                </div>
                <div class="text-xs text-[var(--text-tertiary)] lg:text-right">
                  <div class="mono-data">{{ formatEventOccurredAt(event.occurred_at) }}</div>
                  <div class="mt-2">风控版本：{{ event.risk_rule_version ?? '--' }}</div>
                </div>
              </div>
              <div class="mt-3 text-xs text-[var(--text-tertiary)]">
                策略运行 {{ event.strategy_run_id ?? '--' }} · 订单 {{ event.order_id ?? '--' }} · 成交 {{ event.trade_id ?? '--' }} · correlation {{ event.correlation_id ?? '--' }}
              </div>
            </article>
          </div>
        </div>
        <div v-else class="empty-state !min-h-[180px]">
          <div>{{ eventChainSummary.title }}</div>
          <div class="text-sm text-[var(--text-tertiary)]">{{ eventChainSummary.subtitle }}</div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import {
  fetchBacktestJob,
  fetchBacktestOptimizationHistory,
  fetchBacktestOptimizationJob,
  fetchDailyReviews,
  fetchEquityCurve,
  fetchMonthlyStats,
  fetchPortfolioBacktestJob,
  fetchReportingEvents,
  fetchReportingSummary,
  fetchYearlyStats,
  runBacktest,
  submitBacktestJob,
  submitBacktestOptimizationJob,
  submitPortfolioBacktestJob,
  type BacktestJobResponse,
  type BacktestOptimizationHistoryItem,
  type BacktestOptimizationJobResponse,
  type BacktestOptimizationRequest,
  type BacktestOptimizationResponse,
  type BacktestRunRequest,
  type BacktestRunResponse,
  type PortfolioBacktestRequest,
  type PortfolioBacktestResponse,
} from '../api/backtest'
import { fetchStrategies } from '../api/strategies'
import type { ReportingEvent, ReportingSummary, PeriodStat, EquityCurvePoint } from '../types/reporting'
import type { DailyReviewArchiveItem } from '../api/backtest'
import ChartCard from '../components/ChartCard.vue'
import ErrorAlert from '../components/ErrorAlert.vue'
import MetricCard from '../components/MetricCard.vue'
import PageHeader from '../components/PageHeader.vue'
import { buildAiSuggestionQuery } from '../utils/aiSuggestionContext'
import { formatCurrency, formatPercent } from '../utils/format'
import { getApiErrorMessage } from '../utils/http'

interface ChartCardExpose { initChart: () => Promise<void>; setOption: (option: object) => void }
type Mode = 'single' | 'portfolio' | 'optimization'
type BacktestParameterSource = 'template' | 'example' | 'empty'

interface TemplateBacktestPreset {
  templateKey: string
  templateName: string
  strategyType: NonNullable<BacktestRunRequest['strategy_type']>
  parameters: Record<string, unknown>
}

interface EventChainFilters {
  chainKey: string | null
  strategyRunId: number | null
  orderId: number | null
  correlationId: string | null
}

interface EventChain {
  chainKey: string
  strategyRunId: number | null
  orderId: number | null
  correlationId: string | null
  symbol: string | null
  events: ReportingEvent[]
  lastOccurredAt: string
}

interface EventChainSummary {
  title: string
  subtitle: string
  fallbackReason: string | null
  eventCount: number
  signalCount: number
  riskDecision: string | null
  tradeCount: number
  positionCount: number
  snapshotCount: number
  orderStatus: string | null
}

const modeOptions = [{ label: '单标的', value: 'single' }, { label: '组合', value: 'portfolio' }, { label: '参数扫描', value: 'optimization' }] as const
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const exportingCsv = ref(false)
const mode = ref<Mode>('single')
const route = useRoute()
const summary = ref<ReportingSummary>({ trade_count: 0, realized_pnl: 0, win_rate: 0, cumulative_return: 0, profit_factor: 0, max_drawdown: 0, avg_win: 0, avg_loss: 0, annualized_return_pct: null, annualized_volatility_pct: null, sharpe_ratio: null, calmar_ratio: null })
const equityCurve = ref<EquityCurvePoint[]>([])
const monthlyStats = ref<PeriodStat[]>([])
const yearlyStats = ref<PeriodStat[]>([])
const reportingEvents = ref<ReportingEvent[]>([])
const reportingEventsLoading = ref(false)
const reportingEventsError = ref('')
const backtestResult = ref<BacktestRunResponse | null>(null)
const portfolioResult = ref<PortfolioBacktestResponse | null>(null)
const optimizationResult = ref<BacktestOptimizationResponse | null>(null)
const activeJob = ref<BacktestJobResponse | BacktestOptimizationJobResponse | null>(null)
const optimizationHistory = ref<BacktestOptimizationHistoryItem[]>([])
const configuredStrategies = ref<Array<{ id: number; name: string; strategy_type: string }>>([])
const dailyReviews = ref<DailyReviewArchiveItem[]>([])
const equityChartRef = ref<ChartCardExpose | null>(null)
const monthlyChartRef = ref<ChartCardExpose | null>(null)

const defaultBacktestEndDate = formatDateInput(new Date())
const defaultBacktestStartDate = formatDateInput(new Date(new Date().getFullYear() - 1, 0, 1))
const currentStartDate = computed({ get: () => mode.value === 'portfolio' || mode.value === 'optimization' ? (mode.value === 'portfolio' ? portfolioForm.value.start_date : optimizationForm.value.start_date) : backtestForm.value.start_date, set: (value: string) => { if (mode.value === 'portfolio') portfolioForm.value.start_date = value; else if (mode.value === 'optimization') optimizationForm.value.start_date = value; else backtestForm.value.start_date = value } })
const currentEndDate = computed({ get: () => mode.value === 'portfolio' || mode.value === 'optimization' ? (mode.value === 'portfolio' ? portfolioForm.value.end_date : optimizationForm.value.end_date) : backtestForm.value.end_date, set: (value: string) => { if (mode.value === 'portfolio') portfolioForm.value.end_date = value; else if (mode.value === 'optimization') optimizationForm.value.end_date = value; else backtestForm.value.end_date = value } })

const backtestForm = ref({ symbol: 'sh600519', strategy_id: 0, strategy_type: 'moving_average' as NonNullable<BacktestRunRequest['strategy_type']>, start_date: defaultBacktestStartDate, end_date: defaultBacktestEndDate, use_example_parameters: true, max_position_enabled: true })
const portfolioForm = ref({ symbols: 'sh600519, sz000001', weights: '', start_date: defaultBacktestStartDate, end_date: defaultBacktestEndDate })
const optimizationForm = ref({ symbol: 'sh600519', strategy_type: 'moving_average' as NonNullable<BacktestRunRequest['strategy_type']>, start_date: defaultBacktestStartDate, end_date: defaultBacktestEndDate, target_metric: 'total_return_pct' as BacktestOptimizationRequest['target_metric'], sort_direction: 'desc' as BacktestOptimizationRequest['sort_direction'], gridText: 'short_window=3|5, position_pct=0.1|0.2' })
const activeTemplatePreset = ref<TemplateBacktestPreset | null>(null)

const selectedBacktestStrategy = computed(() => configuredStrategies.value.find((strategy) => strategy.id === backtestForm.value.strategy_id) ?? null)
const actionButtonText = computed(() => mode.value === 'single' ? '运行回测' : mode.value === 'portfolio' ? '运行组合回测' : '运行参数扫描')
const hasTemplateParameters = computed(() => Boolean(activeTemplatePreset.value && Object.keys(activeTemplatePreset.value.parameters).length))
const templateContextQuery = computed(() => buildTemplateContextQuery())
const eventChainFilters = computed(() => readEventChainFilters(route.query))
const eventChains = computed(() => buildEventChains(reportingEvents.value))
const activeEventChain = computed(() => {
  if (!eventChains.value.length) {
    return null
  }
  if (eventChainFilters.value.chainKey) {
    return eventChains.value.find((chain) => chain.chainKey === eventChainFilters.value.chainKey) ?? eventChains.value[0]
  }
  return eventChains.value[0]
})
const eventChainSummary = computed(() => summarizeEventChain(activeEventChain.value))
const eventChainAiQuery = computed(() => buildEventChainAiQuery())
const portfolioSummaryWeightMap = computed(() => Object.fromEntries((portfolioResult.value?.symbols ?? []).map((symbol, index) => [symbol, portfolioResult.value?.weights[index] ?? 0])))
const portfolioContributions = computed<Array<{ symbol: string; pnl: number; total_return_pct: number }>>(() => {
  const contributions = portfolioResult.value?.summary?.contributions
  return Array.isArray(contributions) ? contributions.map((item) => {
    const row = item as Record<string, unknown>
    return {
      symbol: String(row.symbol ?? ''),
      pnl: typeof row.pnl === 'number' ? row.pnl : 0,
      total_return_pct: typeof row.total_return_pct === 'number' ? row.total_return_pct : 0,
    }
  }) : []
})

onMounted(() => {
  void loadAnalysisData()
  void loadConfiguredStrategies()
  void loadOptimizationHistory()
  applyTemplatePresetFromQuery(route.query)
})

watch(() => route.query, (query) => {
  applyTemplatePresetFromQuery(query)
  void refreshReportingEvents()
})

onBeforeUnmount(() => {
  stopBacktestPolling()
})

async function loadAnalysisData(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const [summaryData, curveData, monthlyData, yearlyData, reviews, eventData] = await Promise.all([
      fetchReportingSummary(),
      fetchEquityCurve(),
      fetchMonthlyStats(),
      fetchYearlyStats(),
      fetchDailyReviews({ limit: 10 }),
      loadReportingEvents(),
    ])
    summary.value = summaryData
    equityCurve.value = curveData
    monthlyStats.value = monthlyData
    yearlyStats.value = yearlyData
    dailyReviews.value = reviews.reviews
    reportingEvents.value = eventData
    await renderCharts()
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : '复盘数据加载失败'
  } finally {
    loading.value = false
  }
}

async function loadConfiguredStrategies(): Promise<void> {
  try { configuredStrategies.value = await fetchStrategies() } catch { configuredStrategies.value = [] }
}

async function loadOptimizationHistory(): Promise<void> {
  try { optimizationHistory.value = await fetchBacktestOptimizationHistory() } catch { optimizationHistory.value = [] }
}

async function loadReportingEvents(): Promise<ReportingEvent[]> {
  reportingEventsLoading.value = true
  reportingEventsError.value = ''
  try {
    const params: Record<string, number | string> = {}
    if (eventChainFilters.value.strategyRunId !== null) {
      params.strategy_run_id = eventChainFilters.value.strategyRunId
    }
    if (eventChainFilters.value.orderId !== null) {
      params.order_id = eventChainFilters.value.orderId
    }
    if (eventChainFilters.value.correlationId) {
      params.correlation_id = eventChainFilters.value.correlationId
    }
    const data = await fetchReportingEvents(Object.keys(params).length > 0 ? params : undefined)
    return data
  } catch (err: unknown) {
    reportingEventsError.value = getApiErrorMessage(err, '事件链加载失败')
    return []
  } finally {
    reportingEventsLoading.value = false
  }
}

async function refreshReportingEvents(): Promise<void> {
  reportingEvents.value = await loadReportingEvents()
}

async function exportTradesCsv(): Promise<void> {
  exportingCsv.value = true
  try { const { downloadTradesCsv } = await import('../api/reporting'); await downloadTradesCsv() } finally { exportingCsv.value = false }
}

async function runAnalysis(): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    if (mode.value === 'single') {
      backtestResult.value = null
      const payload = buildBacktestPayload()
      if (backtestForm.value.strategy_id > 0) { const job = await submitBacktestJob(payload); activeJob.value = job; backtestResult.value = (await fetchBacktestJob(job.job_id)).result as BacktestRunResponse | null } else { backtestResult.value = await runBacktest(payload) }
      return
    }
    if (mode.value === 'portfolio') {
      const payload = buildPortfolioPayload()
      const job = await submitPortfolioBacktestJob(payload)
      activeJob.value = job
      portfolioResult.value = (await fetchPortfolioBacktestJob(job.job_id)).result as PortfolioBacktestResponse | null
      return
    }
    const payload = buildOptimizationPayload()
    const job = await submitBacktestOptimizationJob(payload)
    activeJob.value = job
    optimizationResult.value = (await fetchBacktestOptimizationJob(job.job_id)).result
    await loadOptimizationHistory()
  } catch (err: unknown) {
    error.value = getApiErrorMessage(err, '任务执行失败')
  } finally {
    busy.value = false
  }
}

async function loadLatestJob(): Promise<void> {
  try {
    const { fetchLatestBacktestOptimizationJob } = await import('../api/backtest')
    activeJob.value = await fetchLatestBacktestOptimizationJob()
    optimizationResult.value = (activeJob.value as BacktestOptimizationJobResponse | null)?.result ?? null
  } catch (err: unknown) {
    error.value = getApiErrorMessage(err, '最新任务加载失败')
  }
}

function buildTemplateContextQuery(): Record<string, string> | undefined {
  if (mode.value !== 'single' || !activeTemplatePreset.value) {
    return undefined
  }
  const templateParameters = JSON.stringify(activeTemplatePreset.value.parameters ?? {})
  return buildAiSuggestionQuery({
    symbol: backtestForm.value.symbol,
    strategyType: backtestForm.value.strategy_type,
    templateKey: activeTemplatePreset.value.templateKey,
    templateName: activeTemplatePreset.value.templateName,
    templateParameters,
    currentParameters: templateParameters,
    parameterSource: 'template',
    source: 'strategy-template',
  })
}

function buildBacktestPayload(): BacktestRunRequest {
  const parameterSource = resolveBacktestParameterSource()
  const payload: BacktestRunRequest = {
    symbol: backtestForm.value.symbol,
    strategy_type: backtestForm.value.strategy_type,
    start_date: backtestForm.value.start_date || null,
    end_date: backtestForm.value.end_date || null,
    initial_cash: 100000,
    commission_rate: 0.0003,
    slippage_rate: 0.0002,
    max_position_pct: backtestForm.value.max_position_enabled ? 0.6 : 1,
    parameters: parameterSource === 'template'
      ? { ...(activeTemplatePreset.value?.parameters ?? {}) }
      : parameterSource === 'example'
        ? buildExampleParameters()
        : {},
  }
  if (backtestForm.value.strategy_id > 0) { payload.strategy_id = backtestForm.value.strategy_id; payload.strategy_type = (selectedBacktestStrategy.value?.strategy_type as BacktestRunRequest['strategy_type'] | undefined) ?? payload.strategy_type; payload.parameters = undefined }
  return payload
}

function resolveBacktestParameterSource(): BacktestParameterSource {
  if (hasTemplateParameters.value) {
    return 'template'
  }
  if (backtestForm.value.use_example_parameters) {
    return 'example'
  }
  return 'empty'
}

function buildExampleParameters(): Record<string, unknown> {
  return { short_window: 5, long_window: 20, position_pct: 0.1 }
}

function buildPortfolioPayload(): PortfolioBacktestRequest {
  const symbols = portfolioForm.value.symbols.split(/[\s,，]+/).map((item) => item.trim()).filter(Boolean)
  const weights = portfolioForm.value.weights.split(/[\s,，]+/).map((item) => Number(item)).filter((item) => Number.isFinite(item) && item > 0)
  return { symbol: symbols[0] || '', symbols, weights: weights.length === symbols.length ? weights : null, strategy_type: backtestForm.value.strategy_type, start_date: portfolioForm.value.start_date || null, end_date: portfolioForm.value.end_date || null, initial_cash: 100000, commission_rate: 0.0003, slippage_rate: 0.0002, max_position_pct: 0.6, parameters: { short_window: 5, long_window: 20, position_pct: 0.1 } }
}

function buildOptimizationPayload(): BacktestOptimizationRequest {
  return { symbol: optimizationForm.value.symbol, strategy_type: optimizationForm.value.strategy_type, start_date: optimizationForm.value.start_date || null, end_date: optimizationForm.value.end_date || null, initial_cash: 100000, commission_rate: 0.0003, slippage_rate: 0.0002, max_position_pct: 0.6, parameters: { long_window: 20 }, parameter_grid: parseGridText(optimizationForm.value.gridText), target_metric: optimizationForm.value.target_metric, sort_direction: optimizationForm.value.sort_direction, out_of_sample: null }
}

function parseGridText(text: string): Record<string, Array<string | number | boolean | null>> { const grid: Record<string, Array<string | number | boolean | null>> = {}; text.split(',').map((item) => item.trim()).filter(Boolean).forEach((chunk) => { const [key, rawValues] = chunk.split('='); if (!key || !rawValues) return; grid[key.trim()] = rawValues.split('|').map((value) => { const trimmed = value.trim(); if (trimmed === 'true') return true; if (trimmed === 'false') return false; const numberValue = Number(trimmed); return Number.isFinite(numberValue) ? numberValue : trimmed }) }); return grid }
function formatObject(value: Record<string, unknown> | null | undefined): string { if (!value || Object.keys(value).length === 0) return '--'; return Object.entries(value).map(([key, item]) => `${key}:${item}`).join(' · ') }
function formatOptimizationMetric(value: number | undefined | null): string { return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(4) : '--' }
function displayStrategy(value: string): string { return ({ moving_average: '双均线', macd: 'MACD', rl_trading: 'RL 实验', rsi_reversal: 'RSI', bollinger_band: '布林带', kdj_momentum: 'KDJ', signal_fusion: '多信号融合' } as Record<string, string>)[value] ?? value }
function statusText(status: string): string { return ({ queued: '排队中', running: '运行中', succeeded: '已完成', failed: '失败' } as Record<string, string>)[status] ?? status }
function formatDateInput(value: Date): string { return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}` }
function syncBacktestStrategyType(): void { if (selectedBacktestStrategy.value) backtestForm.value.strategy_type = selectedBacktestStrategy.value.strategy_type as NonNullable<BacktestRunRequest['strategy_type']> }
function applyTemplatePresetFromQuery(query: Record<string, unknown>): void {
  const modeValue = firstQueryValue(query.mode)
  const sourceValue = firstQueryValue(query.source)
  if (modeValue !== 'single' || sourceValue !== 'strategy-template') {
    activeTemplatePreset.value = null
    return
  }

  const symbolValue = firstQueryValue(query.symbol)
  const strategyType = toStrategyType(firstQueryValue(query.strategyType))
  const templateKey = firstQueryValue(query.templateKey)
  const templateName = firstQueryValue(query.templateName)
  const templateParameters = parseTemplateParameters(firstQueryValue(query.templateParameters))

  if (!strategyType || !templateKey || !templateName) {
    activeTemplatePreset.value = null
    return
  }

  mode.value = 'single'
  backtestForm.value.strategy_id = 0
  backtestForm.value.symbol = symbolValue || backtestForm.value.symbol
  backtestForm.value.strategy_type = strategyType
  backtestForm.value.use_example_parameters = false
  activeTemplatePreset.value = {
    templateKey,
    templateName,
    strategyType,
    parameters: templateParameters,
  }
}

function firstQueryValue(value: unknown): string {
  if (Array.isArray(value)) {
    return typeof value[0] === 'string' ? value[0] : ''
  }
  return typeof value === 'string' ? value : ''
}

function parseTemplateParameters(raw: string): Record<string, unknown> {
  if (!raw) {
    return {}
  }
  try {
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {}
  } catch {
    return {}
  }
}

function toStrategyType(value: string): NonNullable<BacktestRunRequest['strategy_type']> | null {
  return ['moving_average', 'macd', 'rl_trading', 'rsi_reversal', 'bollinger_band', 'kdj_momentum', 'signal_fusion'].includes(value)
    ? value as NonNullable<BacktestRunRequest['strategy_type']>
    : null
}

function readEventChainFilters(query: Record<string, unknown>): EventChainFilters {
  const correlationId = firstQueryValue(query.correlationId) || null
  const orderId = parseQueryNumber(query.orderId)
  const strategyRunId = parseQueryNumber(query.strategyRunId)
  const chainKey = correlationId
    ? `correlation:${correlationId}`
    : orderId !== null
      ? `order:${orderId}`
      : strategyRunId !== null
        ? `run:${strategyRunId}`
        : null
  return { chainKey, strategyRunId, orderId, correlationId }
}

function parseQueryNumber(value: unknown): number | null {
  const raw = firstQueryValue(value)
  if (!raw) {
    return null
  }
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : null
}

function eventChainKey(event: ReportingEvent): string {
  if (event.correlation_id) {
    return `correlation:${event.correlation_id}`
  }
  if (event.order_id !== null) {
    return `order:${event.order_id}`
  }
  if (event.strategy_run_id !== null) {
    return `run:${event.strategy_run_id}`
  }
  return `event:${event.id}`
}

function buildEventChains(events: ReportingEvent[]): EventChain[] {
  const grouped = new Map<string, EventChain>()
  const sorted = [...events].sort((left, right) => {
    const timeOrder = left.occurred_at.localeCompare(right.occurred_at)
    return timeOrder !== 0 ? timeOrder : left.id - right.id
  })
  for (const event of sorted) {
    const chainKey = eventChainKey(event)
    const current = grouped.get(chainKey)
    if (current) {
      current.events.push(event)
      current.lastOccurredAt = event.occurred_at
      if (!current.symbol && event.symbol) {
        current.symbol = event.symbol
      }
      if (current.strategyRunId === null && event.strategy_run_id !== null) {
        current.strategyRunId = event.strategy_run_id
      }
      if (current.orderId === null && event.order_id !== null) {
        current.orderId = event.order_id
      }
      if (current.correlationId === null && event.correlation_id) {
        current.correlationId = event.correlation_id
      }
      continue
    }
    grouped.set(chainKey, {
      chainKey,
      strategyRunId: event.strategy_run_id,
      orderId: event.order_id,
      correlationId: event.correlation_id,
      symbol: event.symbol,
      events: [event],
      lastOccurredAt: event.occurred_at,
    })
  }
  return [...grouped.values()].sort((left, right) => {
    const timeOrder = right.lastOccurredAt.localeCompare(left.lastOccurredAt)
    return timeOrder !== 0 ? timeOrder : right.events[right.events.length - 1].id - left.events[left.events.length - 1].id
  })
}

function summarizeEventChain(chain: EventChain | null): EventChainSummary {
  if (!chain) {
    return {
      title: '暂无事件链',
      subtitle: '当前复盘页还没有可聚合的策略 / 订单 / 成交链路。',
      fallbackReason: eventChainFilters.value.chainKey ? '未找到匹配链路，请检查 query 中的 strategyRunId / orderId / correlationId。' : null,
      eventCount: 0,
      signalCount: 0,
      riskDecision: null,
      tradeCount: 0,
      positionCount: 0,
      snapshotCount: 0,
      orderStatus: null,
    }
  }

  const riskEvent = chain.events.find((event) => event.event_type === 'risk_decision')
  const latestOrderEvent = [...chain.events].reverse().find((event) => event.event_type === 'order_event')
  return {
    title: `${chain.symbol ?? '--'} · ${chainLabel(chain)}`,
    subtitle: [
      chain.strategyRunId !== null ? `策略运行 ${chain.strategyRunId}` : '无策略运行 ID',
      chain.orderId !== null ? `订单 ${chain.orderId}` : '无订单 ID',
      chain.correlationId ? `链路 ${chain.correlationId.slice(0, 12)}` : '无 correlation_id',
    ].join(' · '),
    fallbackReason: chain.events.map((event) => readDegradedReason(event)).find((item) => item) ?? null,
    eventCount: chain.events.length,
    signalCount: chain.events.filter((event) => event.event_type === 'strategy_signal').length,
    riskDecision: readPayloadString(riskEvent?.payload, 'decision'),
    tradeCount: chain.events.filter((event) => event.event_type === 'trade_execution').length,
    positionCount: chain.events.filter((event) => event.event_type === 'position_change').length,
    snapshotCount: chain.events.filter((event) => event.event_type === 'equity_snapshot').length,
    orderStatus: readPayloadString(latestOrderEvent?.payload, 'to_status'),
  }
}

function chainLabel(chain: EventChain): string {
  if (chain.correlationId) {
    return `correlation ${chain.correlationId.slice(0, 8)}`
  }
  if (chain.orderId !== null) {
    return `order ${chain.orderId}`
  }
  if (chain.strategyRunId !== null) {
    return `run ${chain.strategyRunId}`
  }
  return 'unscoped'
}

function buildEventChainAiQuery(): Record<string, string> | undefined {
  if (!activeEventChain.value) {
    return undefined
  }
  const symbol = activeEventChain.value.symbol ?? backtestForm.value.symbol
  if (!symbol) {
    return undefined
  }
  const currentParameters = mode.value === 'single' ? buildBacktestPayload().parameters : {}
  return buildAiSuggestionQuery({
    symbol,
    strategyType: backtestForm.value.strategy_type,
    currentParameters: currentParameters && Object.keys(currentParameters).length ? JSON.stringify(currentParameters) : null,
    parameterSource: mode.value === 'single' ? resolveBacktestParameterSource() : null,
    source: 'backtest-result',
    strategyRunId: activeEventChain.value.strategyRunId,
    orderId: activeEventChain.value.orderId,
    correlationId: activeEventChain.value.correlationId,
  })
}

function formatEventOccurredAt(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function eventTypeLabel(eventType: string): string {
  return ({
    strategy_signal: '策略信号',
    risk_decision: '风控决策',
    order_event: '订单状态',
    trade_execution: '成交',
    position_change: '持仓变化',
    equity_snapshot: '权益快照',
  } as Record<string, string>)[eventType] ?? eventType
}

function summarizeReportingEvent(event: ReportingEvent): string {
  if (event.event_type === 'strategy_signal') {
    return [
      readPayloadString(event.payload, 'signal') ?? 'signal=--',
      readPayloadString(event.payload, 'reason') ?? readPayloadString(event.payload, 'trigger_reason') ?? '缺少触发原因',
      formatStringList(readPayloadStringArray(event.payload, 'execution_blockers')),
    ].filter(Boolean).join(' · ')
  }
  if (event.event_type === 'risk_decision') {
    return [
      readPayloadString(event.payload, 'decision') ?? 'decision=--',
      readPayloadString(event.payload, 'rejection_reason') ?? '通过',
      `规则 ${event.risk_rule_version ?? readPayloadString(event.payload, 'risk_rule_version') ?? '--'}`,
    ].join(' · ')
  }
  if (event.event_type === 'order_event') {
    return [
      readPayloadString(event.payload, 'event_type') ?? '--',
      `${readPayloadString(event.payload, 'from_status') ?? '--'} -> ${readPayloadString(event.payload, 'to_status') ?? '--'}`,
      readPayloadString(event.payload, 'reason') ?? '',
    ].filter(Boolean).join(' · ')
  }
  if (event.event_type === 'trade_execution') {
    return [
      `${readPayloadNumber(event.payload, 'quantity') ?? '--'} 股`,
      formatMaybeCurrency(readPayloadNumber(event.payload, 'price')),
      `费用 ${formatMaybeCurrency(readPayloadNumber(event.payload, 'fee'))}`,
    ].join(' · ')
  }
  if (event.event_type === 'position_change') {
    return [
      `仓位 ${readPayloadNumber(event.payload, 'quantity') ?? '--'} 股`,
      `可卖 ${readPayloadNumber(event.payload, 'available_quantity') ?? '--'} 股`,
      `成本 ${formatMaybeCurrency(readPayloadNumber(event.payload, 'average_cost'))}`,
    ].join(' · ')
  }
  if (event.event_type === 'equity_snapshot') {
    return [
      `权益 ${formatMaybeCurrency(readPayloadNumber(event.payload, 'total_equity'))}`,
      `现金 ${formatMaybeCurrency(readPayloadNumber(event.payload, 'available_cash'))}`,
      `市值 ${formatMaybeCurrency(readPayloadNumber(event.payload, 'market_value'))}`,
    ].join(' · ')
  }
  return formatObject(event.payload)
}

function readDegradedReason(event: ReportingEvent): string | null {
  return readPayloadString(event.payload, 'degraded_reason')
}

function readPayloadString(payload: Record<string, unknown> | undefined, key: string): string | null {
  if (!payload) {
    return null
  }
  const value = payload[key]
  return typeof value === 'string' && value.trim() ? value : null
}

function readPayloadNumber(payload: Record<string, unknown> | undefined, key: string): number | null {
  if (!payload) {
    return null
  }
  const value = payload[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function readPayloadStringArray(payload: Record<string, unknown> | undefined, key: string): string[] {
  if (!payload) {
    return []
  }
  const value = payload[key]
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0) : []
}

function formatStringList(items: string[]): string {
  return items.length ? items.join(' / ') : ''
}

function formatMaybeCurrency(value: number | null): string {
  return value === null ? '--' : formatCurrency(value)
}

function stopBacktestPolling(): void {}
async function renderCharts(): Promise<void> { await nextTick(); if (equityChartRef.value) { await equityChartRef.value.initChart(); equityChartRef.value.setOption(buildEquityOption()) }; if (monthlyChartRef.value) { await monthlyChartRef.value.initChart(); monthlyChartRef.value.setOption(buildMonthlyOption()) } }
function buildEquityOption(): object { const rows = mode.value === 'portfolio' ? portfolioResult.value?.equity_curve ?? [] : backtestResult.value?.equity_curve ?? []; return { backgroundColor: 'transparent', tooltip: { trigger: 'axis', backgroundColor: 'rgba(7, 14, 25, 0.94)', borderColor: 'rgba(121, 168, 220, 0.22)', textStyle: { color: '#dbe7f5' } }, grid: { left: 14, right: 18, top: 24, bottom: 20, containLabel: true }, xAxis: { type: 'category', boundaryGap: false, data: rows.map((row) => String(row.trade_date ?? row.date ?? row.label ?? '')), axisLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } }, axisLabel: { color: '#6f86a4' } }, yAxis: { type: 'value', splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } }, axisLabel: { color: '#6f86a4', formatter: (value: number) => `${(value / 10000).toFixed(1)}w` } }, series: [{ type: 'line', smooth: true, symbol: 'none', lineStyle: { width: 3, color: '#67b7ff' }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(103, 183, 255, 0.34)' }, { offset: 1, color: 'rgba(103, 183, 255, 0.02)' }] } }, data: rows.map((row) => Number(row.net_worth ?? row.total_equity ?? row.equity ?? 0)) }] } }
function buildMonthlyOption(): object { return { backgroundColor: 'transparent', tooltip: { trigger: 'axis', backgroundColor: 'rgba(7, 14, 25, 0.94)', borderColor: 'rgba(121, 168, 220, 0.22)', textStyle: { color: '#dbe7f5' }, valueFormatter: (value: number) => formatCurrency(value) }, grid: { left: 14, right: 18, top: 24, bottom: 20, containLabel: true }, xAxis: { type: 'category', data: monthlyStats.value.map((item) => item.period), axisLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } }, axisLabel: { color: '#6f86a4' } }, yAxis: { type: 'value', splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } }, axisLabel: { color: '#6f86a4', formatter: (value: number) => `${(value / 1000).toFixed(0)}k` } }, series: [{ type: 'line', smooth: true, symbolSize: 8, lineStyle: { width: 3, color: '#3fd0a4' }, itemStyle: { color: '#3fd0a4' }, data: monthlyStats.value.map((item) => item.realized_pnl) }] } }
</script>
