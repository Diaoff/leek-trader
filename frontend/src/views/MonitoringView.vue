<template>
  <section class="space-y-6">
    <PageHeader
      title="运行治理"
      subtitle="集中查看核心运行指标、异步任务状态、系统健康和最新日志，方便快速定位问题。"
    />

    <ErrorAlert v-if="errorMessage" :message="errorMessage" type="error" />
    <SuccessAlert v-if="lastUpdatedMessage" :message="lastUpdatedMessage" type="success" />

    <div class="flex flex-wrap items-center gap-3">
      <button class="primary-button" type="button" :disabled="loading" @click="loadMonitoringData">
        {{ loading ? '刷新中...' : '刷新面板' }}
      </button>
      <span class="status-chip subtle">窗口 {{ metrics?.window_days ?? windowDays }} 天</span>
      <span class="status-chip subtle">任务 {{ taskSummary?.panel.task_count ?? 0 }} 项</span>
      <span :class="['status-chip', healthToneClass]">{{ healthLabel }}</span>
    </div>

    <div class="grid gap-4 xl:grid-cols-4">
      <MetricCard label="服务状态" :value="metrics?.status ?? 'unknown'" hint="运行指标接口状态" />
      <MetricCard label="最新数据" :value="metrics?.market_data.latest_trade_date ?? '--'" hint="行情质量的最新交易日" />
      <MetricCard label="任务总数" :value="taskSummary?.panel.task_count ?? 0" hint="异步任务摘要总条数" />
      <MetricCard label="进程 PID" :value="systemStats?.pid ?? '--'" hint="仅用于本地定位服务进程" />
    </div>

    <div class="grid gap-6 xl:grid-cols-2">
      <div class="panel space-y-4">
        <div class="panel-header !mb-0">
          <div>
            <div class="section-label">核心指标</div>
            <h3 class="panel-title mt-3">行情、策略、交易</h3>
            <p class="panel-subtitle">按最近 {{ windowDays }} 天聚合核心运行数据。</p>
          </div>
        </div>

        <div class="grid gap-4 md:grid-cols-2">
          <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
            <div class="text-sm text-[var(--text-secondary)]">行情数据</div>
            <div class="mt-2 grid gap-2 text-sm">
              <div class="flex justify-between gap-4"><span>状态</span><strong>{{ metrics?.market_data.status ?? '--' }}</strong></div>
              <div class="flex justify-between gap-4"><span>过期天数</span><strong>{{ metrics?.market_data.staleness_days ?? '--' }}</strong></div>
              <div class="flex justify-between gap-4"><span>日线条数</span><strong>{{ metrics?.market_data.daily_bar_rows ?? 0 }}</strong></div>
              <div class="flex justify-between gap-4"><span>标的数</span><strong>{{ metrics?.market_data.symbol_count ?? 0 }}</strong></div>
              <div class="flex justify-between gap-4"><span>数据源数</span><strong>{{ metrics?.market_data.source_count ?? 0 }}</strong></div>
            </div>
          </div>

          <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
            <div class="text-sm text-[var(--text-secondary)]">策略运行</div>
            <div class="mt-2 grid gap-2 text-sm">
              <div class="flex justify-between gap-4"><span>总运行次数</span><strong>{{ metrics?.strategy_execution.total_runs ?? 0 }}</strong></div>
              <div class="flex justify-between gap-4"><span>成功次数</span><strong>{{ metrics?.strategy_execution.succeeded_runs ?? 0 }}</strong></div>
              <div class="flex justify-between gap-4"><span>失败次数</span><strong>{{ metrics?.strategy_execution.failed_runs ?? 0 }}</strong></div>
              <div class="flex justify-between gap-4"><span>成功率</span><strong>{{ formatPercent(metrics?.strategy_execution.success_rate) }}</strong></div>
              <div class="flex justify-between gap-4"><span>最近运行</span><strong>{{ metrics?.strategy_execution.latest_run_at ?? '--' }}</strong></div>
            </div>
          </div>

          <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
            <div class="text-sm text-[var(--text-secondary)]">交易执行</div>
            <div class="mt-2 grid gap-2 text-sm">
              <div class="flex justify-between gap-4"><span>总委托</span><strong>{{ metrics?.trading.total_orders ?? 0 }}</strong></div>
              <div class="flex justify-between gap-4"><span>已成交</span><strong>{{ metrics?.trading.filled_orders ?? 0 }}</strong></div>
              <div class="flex justify-between gap-4"><span>已拒单</span><strong>{{ metrics?.trading.rejected_orders ?? 0 }}</strong></div>
              <div class="flex justify-between gap-4"><span>成交率</span><strong>{{ formatPercent(metrics?.trading.order_success_rate) }}</strong></div>
              <div class="flex justify-between gap-4"><span>最新成交</span><strong>{{ metrics?.trading.latest_trade_at ?? '--' }}</strong></div>
            </div>
          </div>

          <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
            <div class="text-sm text-[var(--text-secondary)]">系统运行</div>
            <div class="mt-2 grid gap-2 text-sm">
              <div class="flex justify-between gap-4"><span>CPU</span><strong>{{ systemStats?.cpu_percent ?? '--' }}%</strong></div>
              <div class="flex justify-between gap-4"><span>内存</span><strong>{{ systemStats?.memory?.percent ?? '--' }}%</strong></div>
              <div class="flex justify-between gap-4"><span>磁盘</span><strong>{{ systemStats?.disk?.percent ?? '--' }}%</strong></div>
              <div class="flex justify-between gap-4"><span>环境</span><strong>{{ health.environment ?? 'unknown' }}</strong></div>
              <div class="flex justify-between gap-4"><span>租户</span><strong>{{ health.tenant ?? 'unknown' }}</strong></div>
            </div>
          </div>
        </div>
      </div>

      <div class="panel space-y-4">
        <div class="panel-header !mb-0">
          <div>
            <div class="section-label">异步任务</div>
            <h3 class="panel-title mt-3">摘要与最近状态</h3>
            <p class="panel-subtitle">优先读取数据库持久化结果，回退到当前进程统计。</p>
          </div>
          <span class="status-chip subtle">{{ taskSummary?.panel.persisted_stats_enabled ? '已持久化' : '仅进程内' }}</span>
        </div>

        <div class="overflow-hidden rounded-[18px] border border-white/5">
          <table class="data-table monitoring-table">
            <thead>
              <tr>
                <th>任务</th>
                <th>调度</th>
                <th>统计源</th>
                <th>成功/失败</th>
                <th>最近任务</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="task in taskSummary?.tasks ?? []" :key="task.key">
                <td>
                  <div class="font-semibold">{{ task.display_name }}</div>
                  <div class="mono-data muted-text mt-1">{{ task.task_name }}</div>
                </td>
                <td>
                  <div>{{ task.schedule_seconds ? `${task.schedule_seconds}s` : task.schedule_cron ?? '--' }}</div>
                </td>
                <td>
                  <span class="status-chip subtle">{{ task.stats_source }}</span>
                </td>
                <td>
                  <div>{{ task.stats.succeeded }} / {{ task.stats.failed }}</div>
                  <div class="muted-text text-xs mt-1">重试 {{ task.stats.retried }}</div>
                </td>
                <td>
                  <div class="mono-data">{{ task.stats.last_task_id ?? '--' }}</div>
                  <div class="muted-text text-xs mt-1">{{ task.stats.last_error ?? task.stats.last_retry_error ?? '--' }}</div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
          <div class="text-sm text-[var(--text-secondary)]">摘要备注</div>
          <p class="mt-2 text-sm leading-6 text-[var(--text-primary)]">{{ taskSummary?.note ?? '--' }}</p>
        </div>
      </div>
    </div>

    <div class="grid gap-6 xl:grid-cols-2">
      <div class="panel space-y-4">
        <div class="panel-header !mb-0">
          <div>
            <div class="section-label">数据源能力</div>
            <h3 class="panel-title mt-3">Provider 矩阵</h3>
            <p class="panel-subtitle">聚合行情、历史与研究 provider 的已声明能力，便于核对可用边界。</p>
          </div>
          <span class="status-chip subtle">{{ providerCapabilities?.providers.length ?? 0 }} 个</span>
        </div>
        <div class="grid gap-3">
          <div
            v-for="provider in providerCapabilities?.providers ?? []"
            :key="provider.name"
            class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4"
          >
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div class="font-semibold">{{ provider.label }}</div>
                <div class="mono-data muted-text mt-1">{{ provider.name }}</div>
              </div>
              <div class="flex flex-wrap gap-2">
                <span class="status-chip subtle">{{ provider.supports_adjustment ? '支持复权' : '不支持复权' }}</span>
                <span class="status-chip subtle">{{ provider.stable_for_backtest ? '可用于回测' : '研究辅助/兜底' }}</span>
                <span class="status-chip subtle">{{ provider.requires_login ? '需登录' : '免登录' }}</span>
              </div>
            </div>
            <div class="mt-3 flex flex-wrap gap-2">
              <span
                v-for="capability in provider.capabilities.filter((item) => item.supported)"
                :key="`${provider.name}-${capability.name}`"
                class="status-chip neutral"
              >
                {{ capability.name }}
              </span>
              <span v-if="provider.capabilities.every((item) => !item.supported)" class="muted-text text-sm">未声明能力</span>
            </div>
            <p v-if="provider.rate_limit_note" class="mt-3 text-sm text-[var(--text-secondary)]">
              {{ provider.rate_limit_note }}
            </p>
          </div>
        </div>
      </div>

      <div class="panel space-y-4">
        <div class="panel-header !mb-0">
          <div>
            <div class="section-label">数据源健康</div>
            <h3 class="panel-title mt-3">本地日线健康概览</h3>
            <p class="panel-subtitle">不主动探测外部网络，结合本地落库结果和近期运行时事件判断健康状态。</p>
          </div>
          <span :class="['status-chip', sourceHealthToneClass]">{{ sourceHealthLabel }}</span>
        </div>
        <div class="grid gap-3">
          <div
            v-for="item in sourceHealth?.sources ?? []"
            :key="item.source"
            class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4"
          >
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div class="font-semibold">{{ item.label }}</div>
                <div class="mono-data muted-text mt-1">{{ item.source }} · {{ item.role }}</div>
              </div>
              <span :class="['status-chip', healthLevelClass(item.health_level)]">{{ item.health_level }}</span>
            </div>
            <div class="mt-3 grid gap-2 text-sm">
              <div class="flex justify-between gap-4"><span>覆盖率</span><strong>{{ formatPercentNumber(item.coverage_ratio) }}</strong></div>
              <div class="flex justify-between gap-4"><span>空数据率</span><strong>{{ formatPercentNumber(item.empty_ratio) }}</strong></div>
              <div class="flex justify-between gap-4"><span>字段缺失率</span><strong>{{ formatPercentNumber(item.field_missing_ratio) }}</strong></div>
              <div class="flex justify-between gap-4"><span>平均延迟</span><strong>{{ item.avg_latency_ms ? `${item.avg_latency_ms.toFixed(1)}ms` : '--' }}</strong></div>
              <div class="flex justify-between gap-4"><span>近期失败/空响应</span><strong>{{ item.recent_failure_count }}/{{ item.recent_empty_count }}</strong></div>
            </div>
            <p v-if="item.notes.length" class="mt-3 text-sm text-[var(--text-secondary)]">
              {{ item.notes.join('；') }}
            </p>
          </div>
        </div>
      </div>
    </div>

    <div class="grid gap-6 xl:grid-cols-2">
      <div class="panel space-y-4">
        <div class="panel-header !mb-0">
          <div>
            <div class="section-label">最新日志</div>
            <h3 class="panel-title mt-3">最近 {{ logCount }} 行</h3>
            <p class="panel-subtitle">快速定位最近的运行信息和异常提示。</p>
          </div>
        </div>
        <div class="rounded-[18px] border border-white/5 bg-black/20 p-4 font-mono text-xs leading-6 text-[var(--text-secondary)]">
          <div v-if="logs.length === 0" class="text-sm text-[var(--text-secondary)]">暂无日志。</div>
          <pre v-else class="whitespace-pre-wrap">{{ logs.join('') }}</pre>
        </div>
      </div>

      <div class="panel space-y-4">
        <div class="panel-header !mb-0">
          <div>
            <div class="section-label">系统健康</div>
            <h3 class="panel-title mt-3">服务与接口</h3>
            <p class="panel-subtitle">延续全局健康检查，补充当前面板上下文。</p>
          </div>
        </div>
        <div class="grid gap-3 text-sm">
          <div class="sidebar-stat"><span>API</span><span class="mono-data">{{ health.services?.api ?? 'unknown' }}</span></div>
          <div class="sidebar-stat"><span>数据库</span><span class="mono-data">{{ health.services?.database ?? 'unknown' }}</span></div>
          <div class="sidebar-stat"><span>Redis</span><span class="mono-data">{{ health.services?.redis ?? 'unknown' }}</span></div>
          <div class="sidebar-stat"><span>日志目录</span><span class="mono-data">{{ taskSummary?.panel.log_dir ?? '--' }}</span></div>
          <div class="sidebar-stat"><span>最近刷新</span><span class="mono-data">{{ lastUpdatedMessage || '--' }}</span></div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import ErrorAlert from '../components/ErrorAlert.vue'
import MetricCard from '../components/MetricCard.vue'
import PageHeader from '../components/PageHeader.vue'
import SuccessAlert from '../components/SuccessAlert.vue'
import { fetchHealth, type HealthResponse } from '../api/health'
import { fetchMarketSourceHealth, fetchProviderCapabilities, type MarketSourceHealthReport, type ProviderCapabilityMatrix } from '../api/marketProviders'
import { fetchAsyncTaskSummary, fetchMonitoringLogs, fetchOperationsMetrics, fetchSystemStats } from '../api/monitoring'
import type { MonitoringAsyncTaskSummary, MonitoringOperationsMetrics, MonitoringSystemStats } from '../types/monitoring'
import { getApiErrorMessage } from '../utils/http'

const windowDays = 7
const loading = ref(false)
const errorMessage = ref('')
const lastUpdatedMessage = ref('')
const health = ref<HealthResponse>({
  status: 'loading',
  app: '',
  environment: 'unknown',
  tenant: 'unknown',
  services: { api: 'unknown', database: 'unknown', redis: 'unknown' },
})
const metrics = ref<MonitoringOperationsMetrics | null>(null)
const taskSummary = ref<MonitoringAsyncTaskSummary | null>(null)
const logs = ref<string[]>([])
const logCount = ref(20)
const systemStats = ref<MonitoringSystemStats | null>(null)
const providerCapabilities = ref<ProviderCapabilityMatrix | null>(null)
const sourceHealth = ref<MarketSourceHealthReport | null>(null)

const healthLabel = computed(() => {
  if (health.value.status === 'ok') {
    return '在线'
  }
  if (loading.value) {
    return '刷新中'
  }
  return '异常'
})

const healthToneClass = computed(() => {
  if (health.value.status === 'ok') {
    return 'positive'
  }
  if (loading.value) {
    return 'neutral'
  }
  return 'negative'
})

const sourceHealthLabel = computed(() => {
  if (sourceHealth.value?.status === 'healthy') {
    return '健康'
  }
  if (sourceHealth.value?.status === 'degraded') {
    return '降级'
  }
  if (sourceHealth.value?.status === 'empty') {
    return '空数据'
  }
  return '未知'
})

const sourceHealthToneClass = computed(() => {
  if (sourceHealth.value?.status === 'healthy') {
    return 'positive'
  }
  if (sourceHealth.value?.status === 'degraded') {
    return 'neutral'
  }
  return 'negative'
})

async function loadMonitoringData(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    const [healthPayload, metricsPayload, taskPayload, logPayload, systemPayload, capabilityPayload, sourceHealthPayload] = await Promise.all([
      fetchHealth(),
      fetchOperationsMetrics(windowDays),
      fetchAsyncTaskSummary(),
      fetchMonitoringLogs(logCount.value),
      fetchSystemStats(),
      fetchProviderCapabilities(),
      fetchMarketSourceHealth(),
    ])
    health.value = healthPayload
    metrics.value = metricsPayload
    taskSummary.value = taskPayload
    logs.value = logPayload.logs
    logCount.value = logPayload.count
    systemStats.value = systemPayload
    providerCapabilities.value = capabilityPayload
    sourceHealth.value = sourceHealthPayload
    lastUpdatedMessage.value = `最近刷新 ${new Date().toLocaleString('zh-CN')}`
  } catch (error: unknown) {
    errorMessage.value = getApiErrorMessage(error, '运行治理面板加载失败')
  } finally {
    loading.value = false
  }
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '--'
  }
  return `${(value * 100).toFixed(2)}%`
}

function formatPercentNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '--'
  }
  return `${(value * 100).toFixed(1)}%`
}

function healthLevelClass(level: 'healthy' | 'degraded' | 'down'): string {
  if (level === 'healthy') {
    return 'positive'
  }
  if (level === 'degraded') {
    return 'neutral'
  }
  return 'negative'
}

onMounted(() => {
  void loadMonitoringData()
})
</script>
