<template>
  <section class="space-y-6">
    <div class="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
      <PageHeader
        title="回测报告"
        subtitle="按任务 ID 查看异步回测状态、收益曲线、回撤诊断和成交明细。"
      />
      <div class="flex flex-wrap gap-2">
        <RouterLink class="secondary-button" :to="{ name: 'analysis' }">返回复盘</RouterLink>
        <RouterLink v-if="aiSuggestionRoute.query" class="primary-button" :to="aiSuggestionRoute">AI 分析建议</RouterLink>
        <button class="primary-button" type="button" :disabled="loading" @click="loadJob">
          {{ loading ? '刷新中...' : '刷新任务' }}
        </button>
      </div>
    </div>

    <ErrorAlert :message="error" type="error" />

    <div v-if="notFound" class="panel empty-state">
      <div>未找到回测任务</div>
      <div class="text-sm text-[var(--text-tertiary)]">任务记录仅保存在当前后端运行期，请回到盈亏复盘重新提交。</div>
    </div>

    <div v-else-if="job" class="space-y-6">
      <div class="panel space-y-4">
        <div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div class="section-label">Backtest Job</div>
            <h3 class="panel-title mt-2">{{ job.progress_label || statusText(job.status) }}</h3>
            <p class="panel-subtitle mt-2">任务：{{ job.job_id }} · 状态：{{ statusText(job.status) }}</p>
          </div>
          <span :class="['status-chip', job.status === 'succeeded' ? 'positive' : job.status === 'failed' ? 'negative' : 'neutral']">
            {{ Math.round(job.progress_pct) }}%
          </span>
        </div>
        <div class="h-2 overflow-hidden rounded-full bg-white/10">
          <div class="h-full rounded-full bg-[var(--accent-primary)] transition-all" :style="{ width: `${boundedProgress}%` }"></div>
        </div>
        <div class="grid gap-3 text-sm text-[var(--text-secondary)] md:grid-cols-2 xl:grid-cols-4">
          <div>创建：<span class="mono-data">{{ formatTime(job.created_at) }}</span></div>
          <div>开始：<span class="mono-data">{{ formatTime(job.started_at) }}</span></div>
          <div>更新：<span class="mono-data">{{ formatTime(job.updated_at) }}</span></div>
          <div>结束：<span class="mono-data">{{ formatTime(job.finished_at) }}</span></div>
        </div>
        <ul v-if="job.progress_details.length" class="space-y-1 text-sm text-[var(--text-secondary)]">
          <li v-for="detail in job.progress_details" :key="detail">{{ detail }}</li>
        </ul>
        <div v-if="job.error" class="rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-200">
          {{ job.error }}
        </div>
      </div>

      <div v-if="optimizationResult" class="space-y-6">
        <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="最佳指标" :value="formatNumber(optimizationResult.best_candidate?.metric_value)" :hint="optimizationResult.target_metric" />
          <MetricCard label="扫描组合" :value="String(optimizationResult.combinations)" hint="参数网格组合数" />
          <MetricCard label="最佳交易" :value="String(optimizationResult.best_candidate?.trade_count ?? 0)" hint="最佳候选交易数" />
          <MetricCard label="样本长度" :value="String(optimizationResult.bars)" hint="历史日线根数" />
        </div>

        <div class="grid gap-4 lg:grid-cols-2">
          <div class="panel">
            <div class="panel-header"><div><h3 class="panel-title">最佳候选</h3><p class="panel-subtitle">参数扫描不会自动写回策略配置。</p></div></div>
            <div class="space-y-2 text-sm text-[var(--text-secondary)]">
              <div>标的：{{ optimizationResult.symbol }}</div>
              <div>策略：{{ displayStrategy(optimizationResult.strategy_type) }}</div>
              <div>参数：{{ formatObject(optimizationResult.best_candidate?.merged_parameters) }}</div>
              <div v-if="optimizationResult.out_of_sample">样本外：{{ formatNumber(numberValue(optimizationResult.out_of_sample.target_metric_value)) }}</div>
            </div>
          </div>
          <div class="panel">
            <div class="panel-header"><div><h3 class="panel-title">过拟合提示</h3><p class="panel-subtitle">{{ optimizationResult.summary.warning || '建议结合样本外验证观察参数稳定性。' }}</p></div></div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header"><div><h3 class="panel-title">扫描矩阵</h3><p class="panel-subtitle">按目标指标排序后的候选列表。</p></div></div>
          <div class="table-shell">
            <table class="data-table">
              <thead><tr><th>排名</th><th>参数</th><th>指标值</th><th>交易数</th><th>状态</th></tr></thead>
              <tbody>
                <tr v-for="candidate in optimizationResult.candidates" :key="candidate.rank">
                  <td>{{ candidate.rank }}</td>
                  <td>{{ formatObject(candidate.parameters) }}</td>
                  <td class="mono-data">{{ formatNumber(candidate.metric_value) }}</td>
                  <td class="mono-data">{{ candidate.trade_count }}</td>
                  <td>{{ candidate.status }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div v-else-if="result" class="space-y-6">
        <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="最终净值" :value="formatCurrency(result.final_net_worth)" :hint="`初始资金 ${formatCurrency(result.initial_cash)}`" :emphasis-class="result.total_return_pct >= 0 ? 'value-rise' : 'value-fall'" />
          <MetricCard label="总收益率" :value="formatPercent(result.total_return_pct / 100)" :hint="displayBacktestStrategy(result)" :emphasis-class="result.total_return_pct >= 0 ? 'value-rise' : 'value-fall'" />
          <MetricCard label="最大回撤" :value="formatPercent(result.max_drawdown_pct / 100)" hint="事件驱动回放峰谷风险" :emphasis-class="result.max_drawdown_pct <= 10 ? 'value-positive' : 'value-negative'" />
          <MetricCard label="交易笔数" :value="String(result.trade_count)" :hint="`样本 ${result.bars} 根`" emphasis-class="" />
        </div>

        <ChartCard ref="equityChartRef" :title="isPortfolioResult ? '组合权益曲线' : '回测权益曲线'" height="h-80" :loading="loading" />

        <div v-if="researchReport" class="panel">
          <div class="panel-header">
            <div>
              <h3 class="panel-title">一页式研究报告</h3>
              <p class="panel-subtitle">汇总数据源、成交假设、绩效指标和风险提示，可下载 Markdown 保存。</p>
            </div>
            <button class="secondary-button" type="button" @click="downloadResearchReport">下载 Markdown</button>
          </div>
          <pre class="max-h-80 overflow-auto whitespace-pre-wrap rounded-[20px] border border-white/5 bg-black/20 p-4 text-sm leading-6 text-[var(--text-secondary)]">{{ researchReport.content }}</pre>
        </div>

        <div v-if="isPortfolioResult" class="grid gap-4 lg:grid-cols-2">
          <div class="panel">
            <div class="panel-header"><div><h3 class="panel-title">组合权重</h3><p class="panel-subtitle">权重已在后端自动归一化。</p></div></div>
            <div class="space-y-2 text-sm text-[var(--text-secondary)]">
              <div v-for="(weight, symbol) in portfolioWeights" :key="symbol">{{ symbol }} · {{ formatPercent(weight) }}</div>
            </div>
          </div>
          <div class="panel">
            <div class="panel-header"><div><h3 class="panel-title">单标的贡献</h3><p class="panel-subtitle">按静态初始权重拆分资金后的子回测汇总。</p></div></div>
            <div class="space-y-2 text-sm text-[var(--text-secondary)]">
              <div v-for="item in portfolioContributions" :key="item.symbol">{{ item.symbol }} · {{ formatCurrency(item.pnl) }} · {{ formatPercent(item.total_return_pct / 100) }}</div>
            </div>
          </div>
        </div>

        <div class="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.8fr)]">
          <div class="panel">
            <div class="panel-header">
              <div>
                <h3 class="panel-title">近期权益明细</h3>
                <p class="panel-subtitle">展示回测权益曲线最后 10 条记录。</p>
              </div>
            </div>
            <div class="table-shell">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>日期</th>
                    <th>净值</th>
                    <th>仓位</th>
                    <th>回撤</th>
                    <th>信号</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in recentEquityRows" :key="String(row.trade_date ?? row.date ?? row.label)">
                    <td class="mono-data">{{ row.trade_date ?? row.date ?? row.label ?? '--' }}</td>
                    <td class="mono-data">{{ formatCurrency(numberValue(row.net_worth ?? row.total_equity ?? row.equity)) }}</td>
                    <td class="mono-data">{{ formatPercent(numberValue(row.position_pct)) }}</td>
                    <td class="mono-data">{{ formatPercent(numberValue(row.drawdown_pct) / 100) }}</td>
                    <td>{{ row.signal ?? '--' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div class="panel space-y-4">
            <div>
              <div class="section-label">Diagnostics</div>
              <h3 class="panel-title mt-3">回撤与信号诊断</h3>
            </div>
            <div class="rounded-[20px] border border-white/5 bg-white/[0.03] p-4">
              <div class="muted-text text-sm">最大回撤</div>
              <div :class="['mt-2 text-3xl font-semibold tracking-[-0.04em]', result.max_drawdown_pct <= 10 ? 'value-positive' : 'value-negative']">
                {{ formatPercent(result.max_drawdown_pct / 100) }}
              </div>
              <div class="mt-2 text-sm text-[var(--text-tertiary)]">{{ result.symbol }} · {{ result.source }} · {{ result.adjustflag }}</div>
            </div>
            <div class="rounded-[20px] border border-white/5 bg-white/[0.03] p-4 text-sm text-[var(--text-secondary)]">
              <div>信号统计：{{ formatCountMap(diagnostics?.signal_counts) }}</div>
              <div class="mt-2">模型动作：{{ formatCountMap(diagnostics?.rl_action_counts) }}</div>
              <div class="mt-2">未交易原因：{{ formatCountMap(diagnostics?.no_trade_reason_counts) }}</div>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div>
              <h3 class="panel-title">交易明细</h3>
              <p class="panel-subtitle">展示回测结果中的成交记录。</p>
            </div>
          </div>
          <div v-if="result.trades.length === 0" class="empty-state">
            <div>暂无交易记录</div>
            <div class="text-sm text-[var(--text-tertiary)]">当前策略在样本区间内没有产生可执行成交。</div>
          </div>
          <div v-else class="table-shell">
            <table class="data-table">
              <thead>
                <tr>
                  <th>日期</th>
                  <th>方向</th>
                  <th>数量</th>
                  <th>价格</th>
                  <th>金额</th>
                  <th>原因</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(trade, index) in result.trades" :key="`${trade.trade_date ?? trade.date ?? index}-${trade.side ?? trade.action ?? ''}`">
                  <td class="mono-data">{{ trade.trade_date ?? trade.date ?? '--' }}</td>
                  <td>{{ trade.side ?? trade.action ?? '--' }}</td>
                  <td class="mono-data">{{ trade.quantity ?? trade.shares ?? '--' }}</td>
                  <td class="mono-data">{{ formatCurrency(numberValue(trade.price)) }}</td>
                  <td class="mono-data">{{ formatCurrency(numberValue(trade.amount ?? trade.value)) }}</td>
                  <td>{{ trade.reason ?? trade.signal ?? '--' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div v-else class="panel empty-state">
        <div>{{ job.status === 'failed' ? '回测任务失败' : '回测结果生成中' }}</div>
        <div class="text-sm text-[var(--text-tertiary)]">{{ job.status === 'failed' ? (job.error || '请调整参数后重新提交。') : '页面会自动轮询 queued/running 状态。' }}</div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { fetchBacktestJob, fetchBacktestOptimizationJob, fetchPortfolioBacktestJob, type BacktestDiagnostics, type BacktestJobResponse, type BacktestOptimizationJobResponse, type BacktestOptimizationResponse, type BacktestRunResponse, type PortfolioBacktestResponse } from '../api/backtest'
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

const route = useRoute()
const loading = ref(false)
const error = ref('')
const notFound = ref(false)
const job = ref<BacktestJobResponse | BacktestOptimizationJobResponse | null>(null)
const equityChartRef = ref<ChartCardExpose | null>(null)
let pollTimer: number | null = null

const jobId = computed(() => String(route.params.jobId ?? ''))
const result = computed(() => isOptimizationJob(jobId.value) ? null : ((job.value as BacktestJobResponse | null)?.result ?? null))
const optimizationResult = computed(() => isOptimizationJob(jobId.value) ? ((job.value as BacktestOptimizationJobResponse | null)?.result ?? null) : null)
const diagnostics = computed<BacktestDiagnostics | null>(() => result.value?.summary?.diagnostics ?? null)
const researchReport = computed(() => result.value?.summary?.research_report ?? null)
const isPortfolioResult = computed(() => Boolean(result.value && 'symbols' in result.value))
const portfolioWeights = computed<Record<string, number>>(() => {
  const portfolio = result.value as PortfolioBacktestResponse | null
  if (!portfolio || !Array.isArray(portfolio.symbols)) return {}
  return Object.fromEntries(portfolio.symbols.map((symbol, index) => [symbol, portfolio.weights[index] ?? 0]))
})
const portfolioContributions = computed<Array<{ symbol: string; pnl: number; total_return_pct: number }>>(() => {
  const contributions = result.value?.summary?.contributions
  if (!Array.isArray(contributions)) return []
  return contributions.map((item) => {
    const row = item as Record<string, unknown>
    return {
      symbol: String(row.symbol ?? ''),
      pnl: typeof row.pnl === 'number' ? row.pnl : 0,
      total_return_pct: typeof row.total_return_pct === 'number' ? row.total_return_pct : 0,
    }
  })
})
const boundedProgress = computed(() => Math.min(Math.max(job.value?.progress_pct ?? 0, 0), 100))
const aiSuggestionRoute = computed(() => ({
  name: 'ai',
  query: buildAiSuggestionQuery(),
}))
const recentEquityRows = computed(() => (result.value?.equity_curve ?? []).slice(-10))

onMounted(() => {
  void loadJob()
})

onBeforeUnmount(() => {
  stopPolling()
})

watch(jobId, () => {
  stopPolling()
  void loadJob()
})

async function loadJob(): Promise<void> {
  if (!jobId.value) {
    notFound.value = true
    return
  }
  loading.value = true
  error.value = ''
  notFound.value = false
  try {
    const data = await fetchJobById(jobId.value)
    job.value = data
    if (data.status === 'queued' || data.status === 'running') {
      startPolling()
    } else {
      stopPolling()
    }
    await renderEquityChart()
  } catch (err: unknown) {
    stopPolling()
    job.value = null
    const status = typeof err === 'object' && err !== null && 'response' in err ? (err as { response?: { status?: number } }).response?.status : undefined
    if (status === 404) {
      notFound.value = true
      return
    }
    error.value = getApiErrorMessage(err, '回测报告加载失败')
  } finally {
    loading.value = false
  }
}

function startPolling(): void {
  if (pollTimer !== null) {
    return
  }
  pollTimer = window.setInterval(() => {
    void loadJob()
  }, 1500)
}

function stopPolling(): void {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

async function renderEquityChart(): Promise<void> {
  if (!result.value) {
    return
  }
  await nextTick()
  if (!equityChartRef.value) {
    return
  }
  await equityChartRef.value.initChart()
  equityChartRef.value.setOption(buildEquityOption(result.value))
}

function buildEquityOption(backtest: BacktestRunResponse | PortfolioBacktestResponse): object {
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
      data: backtest.equity_curve.map((row) => String(row.trade_date ?? row.date ?? row.label ?? '')),
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
        data: backtest.equity_curve.map((row) => numberValue(row.net_worth ?? row.total_equity ?? row.equity)),
      },
    ],
  }
}

async function fetchJobById(id: string): Promise<BacktestJobResponse | BacktestOptimizationJobResponse> {
  if (isOptimizationJob(id)) return fetchBacktestOptimizationJob(id)
  if (isPortfolioJob(id)) return fetchPortfolioBacktestJob(id)
  return fetchBacktestJob(id)
}

function isPortfolioJob(id: string): boolean {
  return id.startsWith('portfolio-backtest-')
}

function isOptimizationJob(id: string): boolean {
  return id.startsWith('backtest-optimization-')
}

function buildAiSuggestionQuery(): Record<string, string> | undefined {
  if (optimizationResult.value) {
    return {
      symbol: optimizationResult.value.symbol,
      strategyType: optimizationResult.value.strategy_type,
      optimizationJobId: jobId.value,
      currentParameters: JSON.stringify(optimizationResult.value.best_candidate?.merged_parameters ?? {}),
    }
  }
  if (result.value && !isPortfolioResult.value) {
    const parameters = readPayloadParameters(job.value?.payload)
    return {
      symbol: result.value.symbol,
      strategyType: result.value.strategy_type,
      backtestJobId: jobId.value,
      currentParameters: JSON.stringify(parameters),
      ...(Object.keys(parameters).length === 0 ? { parametersMissing: '1' } : {}),
    }
  }
  return undefined
}

function readPayloadParameters(payload: Record<string, unknown> | undefined): Record<string, unknown> {
  const parameters = payload?.parameters
  return parameters && typeof parameters === 'object' && !Array.isArray(parameters) ? parameters as Record<string, unknown> : {}
}

function downloadResearchReport(): void {
  if (!researchReport.value || !result.value) return
  const blob = new Blob([researchReport.value.content], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${result.value.symbol}-backtest-report.md`
  link.click()
  URL.revokeObjectURL(url)
}

function formatObject(value: Record<string, unknown> | null | undefined): string {
  if (!value || Object.keys(value).length === 0) return '--'
  return Object.entries(value).map(([key, item]) => `${key}:${item}`).join(' · ')
}

function formatNumber(value: unknown): string {
  const number = numberValue(value)
  return Number.isFinite(number) ? number.toFixed(4) : '--'
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

function displayBacktestStrategy(backtest: BacktestRunResponse): string {
  return backtest.strategy_name || displayStrategy(backtest.strategy_type)
}

function displayStrategy(value: string): string {
  const mapping: Record<string, string> = {
    moving_average: '双均线',
    macd: 'MACD',
    rl_trading: 'RL 实验',
  }
  return mapping[value] ?? value
}

function formatCountMap(counts?: Record<string, number>): string {
  if (!counts || Object.keys(counts).length === 0) {
    return '--'
  }
  return Object.entries(counts).map(([key, value]) => `${key} ${value}`).join(' · ')
}

function formatTime(value: string | null): string {
  return value ? new Date(value).toLocaleString('zh-CN') : '--'
}

function numberValue(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}
</script>
