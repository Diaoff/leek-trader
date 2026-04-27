<template>
  <section class="space-y-6">
    <div class="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
      <PageHeader
        title="策略中心"
        subtitle="围绕真实策略配置、执行模式、运行结果和启停状态，打通本地模拟交易闭环。"
      />
      <div class="token-row">
        <button class="secondary-button" type="button" :disabled="store.loading" @click="loadStrategies">
          刷新策略
        </button>
        <button class="primary-button" type="button" :disabled="store.loading" @click="openCreateDrawer">
          新建策略
        </button>
      </div>
    </div>

    <ErrorAlert :message="store.error" type="error" />

    <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <MetricCard label="策略总数" :value="store.strategyCount" hint="数据库中的全部策略" />
      <MetricCard label="启用中" :value="store.activeStrategies.length" hint="status = active" emphasis-class="value-positive" />
      <MetricCard label="今日运行次数" :value="todayRunsTotal" hint="所有策略 run_count_today 汇总" />
      <MetricCard label="已有运行结果" :value="strategiesWithRuns" hint="total_run_count > 0 的策略数" />
    </div>

    <div class="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_minmax(340px,0.9fr)]">
      <div class="panel">
        <div class="panel-header">
          <div>
            <h3 class="panel-title">策略全景表</h3>
            <p class="panel-subtitle">页内完成创建、编辑、启停和运行，避免再依赖预置数据或独立弹窗流程。</p>
          </div>
        </div>

        <div v-if="store.strategies.length === 0" class="empty-state">
          <div>暂无策略数据</div>
        </div>
        <div v-else class="table-shell">
          <table class="data-table">
            <thead>
              <tr>
                <th>策略</th>
                <th>状态</th>
                <th>标的</th>
                <th>模式</th>
                <th>最新信号</th>
                <th>今日运行</th>
                <th>累计运行</th>
                <th>最近运行</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="strategy in store.strategies" :key="strategy.id">
                <td>
                  <div class="font-semibold">{{ strategy.name }}</div>
                  <div class="text-xs text-[var(--text-tertiary)]">
                    {{ strategyTypeLabel(strategy.strategy_type) }}
                  </div>
                </td>
                <td>
                  <span :class="['status-chip', statusTone(strategy.status)]">
                    {{ statusLabel(strategy.status) }}
                  </span>
                </td>
                <td>
                  <div class="mono-data">{{ strategy.signal_symbol }}</div>
                  <div class="text-xs text-[var(--text-tertiary)]">{{ strategy.symbol }}</div>
                </td>
                <td>
                  <span :class="['status-chip', strategy.execution_mode === 'auto_trade' ? 'negative' : 'neutral']">
                    {{ executionModeLabel(strategy.execution_mode) }}
                  </span>
                  <div class="mt-1 text-xs text-[var(--text-tertiary)]">
                    {{ formatPositionPct(strategy.parameters) }}
                  </div>
                </td>
                <td>
                  <span :class="['status-chip', signalTone(strategy.latest_signal)]">
                    {{ signalLabel(strategy.latest_signal) }}
                  </span>
                  <div class="mt-1 text-xs text-[var(--text-tertiary)]">
                    {{ strategy.latest_run_status ? runStatusLabel(strategy.latest_run_status) : '尚未运行' }}
                  </div>
                  <div v-if="strategy.latest_signal_summary" class="mt-1 text-xs text-[var(--text-tertiary)]">
                    {{ strategy.latest_signal_summary }}
                  </div>
                </td>
                <td class="mono-data">{{ strategy.run_count_today }}</td>
                <td class="mono-data">{{ strategy.total_run_count }}</td>
                <td class="mono-data">{{ formatTime(strategy.latest_run_at) }}</td>
                <td>
                  <div class="flex flex-wrap gap-2">
                    <button
                      class="secondary-button !min-h-9 px-3 text-xs"
                      type="button"
                      :disabled="store.loading"
                      @click="handleRun(strategy.id)"
                    >
                      运行一次
                    </button>
                    <button
                      class="ghost-button !min-h-9 px-3 text-xs"
                      type="button"
                      :disabled="store.loading"
                      @click="openEditDrawer(strategy)"
                    >
                      编辑
                    </button>
                    <button
                      class="ghost-button !min-h-9 px-3 text-xs"
                      type="button"
                      :disabled="store.loading"
                      @click="toggleStrategy(strategy)"
                    >
                      {{ strategy.status === 'active' ? '暂停' : '启用' }}
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="space-y-4">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3 class="panel-title">最近一次执行</h3>
              <p class="panel-subtitle">优先展示策略运行是否只生成信号，还是已经触发自动交易。</p>
            </div>
          </div>

          <div v-if="!store.lastRunResult" class="empty-state !min-h-[260px]">
            <div>还没有本轮运行结果</div>
            <div class="text-sm text-[var(--text-tertiary)]">点击左侧“运行一次”后，这里会展示执行摘要。</div>
          </div>
          <div v-else class="space-y-4">
            <div class="rounded-[20px] border border-white/5 bg-white/[0.03] p-4">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="muted-text text-sm">执行模式</div>
                  <div class="mt-1 font-semibold">{{ executionModeLabel(store.lastRunResult.execution_mode ?? 'signal_only') }}</div>
                  <div class="mt-2 text-sm text-[var(--text-secondary)]">
                    {{ executionOutcomeLabel(store.lastRunResult) }}
                  </div>
                </div>
                <span :class="['status-chip', signalTone(String(store.lastRunResult.signal.signal ?? 'hold'))]">
                  {{ signalLabel(String(store.lastRunResult.signal.signal ?? 'hold')) }}
                </span>
              </div>

              <div class="mt-4 grid grid-cols-2 gap-3 text-sm">
                <div>
                  <div class="muted-text">运行状态</div>
                  <div class="mt-1 mono-data">{{ runStatusLabel(store.lastRunResult.status) }}</div>
                </div>
                <div>
                  <div class="muted-text">信号强度</div>
                  <div class="mt-1 mono-data">{{ strengthLabel(store.lastRunResult.strength) }}</div>
                </div>
                <div>
                  <div class="muted-text">订单状态</div>
                  <div class="mt-1 mono-data">{{ orderStatusLabel(store.lastRunResult.order_status) }}</div>
                </div>
                <div>
                  <div class="muted-text">方向</div>
                  <div class="mt-1 mono-data">{{ sideLabel(store.lastRunResult.side) }}</div>
                </div>
                <div>
                  <div class="muted-text">数量</div>
                  <div class="mt-1 mono-data">{{ store.lastRunResult.quantity ?? '--' }}</div>
                </div>
                <div>
                  <div class="muted-text">推荐池确认</div>
                  <div class="mt-1 mono-data">{{ recommendationLabel(store.lastRunResult.recommendation_confirmed) }}</div>
                </div>
              </div>

              <div class="mt-4 rounded-[18px] border border-white/5 bg-black/10 p-4 text-sm text-[var(--text-secondary)]">
                <div>触发原因：{{ triggerReasonLabel(store.lastRunResult.trigger_reason) }}</div>
                <div class="mt-2">价格：{{ store.lastRunResult.price ? `¥${store.lastRunResult.price.toFixed(2)}` : '--' }}</div>
                <div class="mt-2">建议仓位：{{ formatSuggestedPosition(store.lastRunResult.position_pct) }}</div>
                <div class="mt-2">止损参考：{{ formatPrice(store.lastRunResult.stop_loss_price) }}</div>
                <div class="mt-2">止盈参考：{{ formatPrice(store.lastRunResult.take_profit_price) }}</div>
                <div class="mt-2">执行结论：{{ reasonLabel(store.lastRunResult.reason) }}</div>
                <div class="mt-2">未执行原因：{{ blockersLabel(store.lastRunResult.execution_blockers) }}</div>
                <div class="mt-2">订单 ID：{{ store.lastRunResult.order_id ?? '--' }}</div>
                <div class="mt-2">运行时间：{{ formatTime(store.lastRunResult.created_at) }}</div>
              </div>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div>
              <h3 class="panel-title">活跃策略卡片</h3>
              <p class="panel-subtitle">快速查看当前启用中的策略参数和执行模式。</p>
            </div>
          </div>

          <div v-if="store.activeStrategies.length === 0" class="empty-state !min-h-[320px]">
            <div>当前没有活跃策略</div>
          </div>
          <div v-else class="space-y-3">
            <div
              v-for="strategy in store.activeStrategies"
              :key="strategy.id"
              class="rounded-[20px] border border-white/5 bg-white/[0.03] p-4"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="font-semibold">{{ strategy.name }}</div>
                  <div class="mt-1 text-sm text-[var(--text-secondary)]">{{ strategy.signal_symbol }}</div>
                </div>
                <span :class="['status-chip', signalTone(strategy.latest_signal)]">
                  {{ signalLabel(strategy.latest_signal) }}
                </span>
              </div>

              <div class="mt-4 grid grid-cols-3 gap-3 text-sm">
                <div>
                  <div class="muted-text">今日运行</div>
                  <div class="mt-1 mono-data">{{ strategy.run_count_today }}</div>
                </div>
                <div>
                  <div class="muted-text">累计运行</div>
                  <div class="mt-1 mono-data">{{ strategy.total_run_count }}</div>
                </div>
                <div>
                  <div class="muted-text">执行模式</div>
                  <div class="mt-1 mono-data">{{ executionModeLabel(strategy.execution_mode) }}</div>
                </div>
              </div>

              <div class="mt-4 text-xs text-[var(--text-tertiary)]">
                最近运行：{{ formatTime(strategy.latest_run_at) }}
              </div>

              <div v-if="strategy.latest_signal_summary" class="mt-2 text-xs text-[var(--text-tertiary)]">
                {{ strategy.latest_signal_summary }}
              </div>

              <div class="mt-4 token-row">
                <span v-for="entry in formatParameters(strategy.parameters)" :key="entry" class="token-chip">
                  {{ entry }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <el-drawer v-model="drawerOpen" :title="editingStrategyId ? '编辑策略' : '新建策略'" direction="rtl" size="420px">
      <form class="space-y-4" @submit.prevent="submitStrategy">
        <div>
          <label class="field-label" for="strategy-name">策略名称</label>
          <input id="strategy-name" v-model.trim="strategyForm.name" class="field-input" type="text" placeholder="例如 趋势跟随策略" />
        </div>

        <div>
          <label class="field-label" for="strategy-symbol">股票代码</label>
          <input id="strategy-symbol" v-model.trim="strategyForm.symbol" class="field-input mono-data" type="text" placeholder="输入带交易所前缀的股票代码" />
        </div>

        <div>
          <label class="field-label" for="strategy-type">策略类型</label>
          <select id="strategy-type" v-model="strategyForm.strategyType" class="field-select" @change="syncParameterDefaults">
            <option value="moving_average">双均线</option>
            <option value="macd">MACD</option>
          </select>
        </div>

        <div>
          <label class="field-label" for="execution-mode">执行模式</label>
          <select id="execution-mode" v-model="strategyForm.executionMode" class="field-select">
            <option value="signal_only">仅信号</option>
            <option value="auto_trade">自动交易</option>
          </select>
          <div class="field-help">`signal_only` 只输出交易计划；`auto_trade` 需同时通过推荐池确认、时段和仓位风控闸门。</div>
        </div>

        <div>
          <label class="field-label" for="position-pct">仓位比例</label>
          <input id="position-pct" v-model.number="strategyForm.positionPct" class="field-input mono-data" type="number" min="0" max="1" step="0.01" />
          <div class="field-help">按 0-1 输入，默认 0.10，表示策略上限仓位；实盘下单会与推荐池建议仓位取更保守值。</div>
        </div>

        <div v-if="strategyForm.strategyType === 'moving_average'" class="grid grid-cols-2 gap-3">
          <div>
            <label class="field-label" for="short-window">短期均线</label>
            <input id="short-window" v-model.number="strategyForm.shortWindow" class="field-input mono-data" type="number" min="1" step="1" />
          </div>
          <div>
            <label class="field-label" for="long-window">长期均线</label>
            <input id="long-window" v-model.number="strategyForm.longWindow" class="field-input mono-data" type="number" min="2" step="1" />
          </div>
        </div>

        <div v-else class="grid grid-cols-3 gap-3">
          <div>
            <label class="field-label" for="fast-period">快线</label>
            <input id="fast-period" v-model.number="strategyForm.fastPeriod" class="field-input mono-data" type="number" min="1" step="1" />
          </div>
          <div>
            <label class="field-label" for="slow-period">慢线</label>
            <input id="slow-period" v-model.number="strategyForm.slowPeriod" class="field-input mono-data" type="number" min="2" step="1" />
          </div>
          <div>
            <label class="field-label" for="signal-period">信号线</label>
            <input id="signal-period" v-model.number="strategyForm.signalPeriod" class="field-input mono-data" type="number" min="1" step="1" />
          </div>
        </div>

        <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4 text-sm text-[var(--text-secondary)]">
          <div>信号参数决定何时触发买入、卖出、减仓或观望。</div>
          <div class="mt-2">执行约束固定启用：新开仓必须进入最新智能选股推荐池，且尾盘不新开仓。</div>
        </div>

        <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4 text-sm text-[var(--text-secondary)]">
          <div>创建后默认仍是草稿状态。</div>
          <div class="mt-2">如需进入异步周期执行，请回到列表点击“启用”。</div>
        </div>

        <div class="flex gap-3">
          <button class="primary-button flex-1" type="submit" :disabled="store.loading || !canSubmit">
            {{ editingStrategyId ? '保存修改' : '创建策略' }}
          </button>
          <button class="secondary-button flex-1" type="button" :disabled="store.loading" @click="closeDrawer">
            取消
          </button>
        </div>
      </form>
    </el-drawer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import ErrorAlert from '../components/ErrorAlert.vue'
import MetricCard from '../components/MetricCard.vue'
import PageHeader from '../components/PageHeader.vue'
import { useStrategyStore } from '../stores/strategies'
import type { StrategyExecutionMode, StrategyItem, StrategyRunResult, StrategySignalAction } from '../types/strategy'

const store = useStrategyStore()
const drawerOpen = ref(false)
const editingStrategyId = ref<number | null>(null)
const strategyForm = reactive({
  name: '',
  symbol: '',
  strategyType: 'moving_average',
  executionMode: 'signal_only' as StrategyExecutionMode,
  positionPct: 0.1,
  shortWindow: 5,
  longWindow: 20,
  fastPeriod: 12,
  slowPeriod: 26,
  signalPeriod: 9,
})

const todayRunsTotal = computed(() => store.strategies.reduce((sum, strategy) => sum + strategy.run_count_today, 0))
const strategiesWithRuns = computed(() => store.strategies.filter((strategy) => strategy.total_run_count > 0).length)
const canSubmit = computed(() => strategyForm.name.trim() && strategyForm.symbol.trim())

onMounted(() => {
  void loadStrategies()
})

async function loadStrategies(): Promise<void> {
  await store.fetchStrategies()
}

async function handleRun(strategyId: number): Promise<void> {
  await store.runStrategy(strategyId)
}

async function toggleStrategy(strategy: StrategyItem): Promise<void> {
  const nextStatus = strategy.status === 'active' ? 'paused' : 'active'
  await store.setStrategyStatus(strategy.id, nextStatus)
}

function openCreateDrawer(): void {
  editingStrategyId.value = null
  resetForm()
  drawerOpen.value = true
}

function openEditDrawer(strategy: StrategyItem): void {
  editingStrategyId.value = strategy.id
  strategyForm.name = strategy.name
  strategyForm.symbol = strategy.symbol
  strategyForm.strategyType = strategy.strategy_type
  strategyForm.executionMode = strategy.execution_mode
  strategyForm.positionPct = Number(strategy.parameters.position_pct ?? 0.1)
  strategyForm.shortWindow = Number(strategy.parameters.short_window ?? 5)
  strategyForm.longWindow = Number(strategy.parameters.long_window ?? 20)
  strategyForm.fastPeriod = Number(strategy.parameters.fast_period ?? 12)
  strategyForm.slowPeriod = Number(strategy.parameters.slow_period ?? 26)
  strategyForm.signalPeriod = Number(strategy.parameters.signal_period ?? 9)
  drawerOpen.value = true
}

function closeDrawer(): void {
  drawerOpen.value = false
}

function resetForm(): void {
  strategyForm.name = ''
  strategyForm.symbol = ''
  strategyForm.strategyType = 'moving_average'
  strategyForm.executionMode = 'signal_only'
  strategyForm.positionPct = 0.1
  strategyForm.shortWindow = 5
  strategyForm.longWindow = 20
  strategyForm.fastPeriod = 12
  strategyForm.slowPeriod = 26
  strategyForm.signalPeriod = 9
}

function syncParameterDefaults(): void {
  if (strategyForm.strategyType === 'moving_average') {
    strategyForm.shortWindow = 5
    strategyForm.longWindow = 20
    return
  }
  strategyForm.fastPeriod = 12
  strategyForm.slowPeriod = 26
  strategyForm.signalPeriod = 9
}

function buildParameters(): Record<string, number> {
  if (strategyForm.strategyType === 'moving_average') {
    return {
      short_window: strategyForm.shortWindow,
      long_window: strategyForm.longWindow,
      position_pct: strategyForm.positionPct,
    }
  }
  return {
    fast_period: strategyForm.fastPeriod,
    slow_period: strategyForm.slowPeriod,
    signal_period: strategyForm.signalPeriod,
    position_pct: strategyForm.positionPct,
  }
}

async function submitStrategy(): Promise<void> {
  const payload = {
    name: strategyForm.name.trim(),
    symbol: strategyForm.symbol.trim(),
    strategy_type: strategyForm.strategyType,
    execution_mode: strategyForm.executionMode,
    parameters: buildParameters(),
  }

  if (editingStrategyId.value === null) {
    await store.createStrategy(payload)
  } else {
    await store.updateStrategy(editingStrategyId.value, payload)
  }
  closeDrawer()
}

function strategyTypeLabel(strategyType: string): string {
  const mapping: Record<string, string> = {
    moving_average: '双均线',
    macd: 'MACD',
  }
  return mapping[strategyType] ?? strategyType
}

function executionModeLabel(mode: StrategyExecutionMode): string {
  return mode === 'auto_trade' ? '自动交易' : '仅信号'
}

function signalLabel(signal: StrategySignalAction | string): string {
  const mapping: Record<string, string> = {
    buy: '买入',
    sell: '卖出',
    reduce: '减仓',
    hold: '观望',
  }
  return mapping[signal] ?? signal
}

function signalTone(signal: string): 'positive' | 'negative' | 'neutral' {
  if (signal === 'buy') {
    return 'positive'
  }
  if (signal === 'sell' || signal === 'reduce') {
    return 'negative'
  }
  return 'neutral'
}

function strengthLabel(strength: string | null): string {
  const mapping: Record<string, string> = {
    strong: '强',
    normal: '中',
    weak: '弱',
  }
  if (!strength) {
    return '--'
  }
  return mapping[strength] ?? strength
}

function statusLabel(status: StrategyItem['status']): string {
  const mapping: Record<StrategyItem['status'], string> = {
    active: '启用中',
    paused: '已暂停',
    draft: '草稿',
  }
  return mapping[status]
}

function statusTone(status: StrategyItem['status']): 'positive' | 'neutral' {
  return status === 'active' ? 'positive' : 'neutral'
}

function runStatusLabel(status: string): string {
  const mapping: Record<string, string> = {
    pending: '排队中',
    success: '成功',
    failed: '失败',
  }
  return mapping[status] ?? status
}

function orderStatusLabel(status: string | null): string {
  if (!status) {
    return '--'
  }
  const mapping: Record<string, string> = {
    filled: '已成交',
    rejected: '已拒绝',
    pending: '待成交',
    cancelled: '已撤销',
  }
  return mapping[status] ?? status
}

function sideLabel(side: string | null): string {
  if (side === 'buy') {
    return '买入'
  }
  if (side === 'sell') {
    return '卖出'
  }
  return '--'
}

function reasonLabel(reason: string | null): string {
  const mapping: Record<string, string> = {
    signal_only_mode: '仅信号模式',
    signal_hold: '当前信号为观望，不触发自动交易',
    order_submitted: '通过闸门并已下单',
    recommendation_missing: '信号成立但未过推荐池',
    recommendation_score_below_threshold: '推荐池评分不足',
    recommendation_timing_not_ready: '推荐池时机未满足',
    quantity_below_min_lot: '信号成立但仓位不足',
    insufficient_cash: '信号成立但仓位不足',
    single_position_limit_exceeded: '单标的仓位上限限制',
    total_exposure_limit_exceeded: '总仓位上限限制',
    opening_window_closed: '尾盘或非允许时段，禁止新开仓',
    outside_trading_hours: '当前不在交易时段',
    t_plus_one_restriction: 'T+1 限制',
    symbol_halted: '标的停牌',
    near_limit_move: '接近涨跌停，跳过开仓',
    limit_up_restriction: '涨停限制',
    limit_down_restriction: '跌停限制',
    insufficient_position: '没有可卖仓位',
    daily_trade_limit_exceeded: '当日交易次数超限',
    daily_loss_circuit_breaker: '触发日内亏损熔断',
  }
  if (!reason) {
    return '--'
  }
  return mapping[reason] ?? reason
}

function blockersLabel(blockers: string[]): string {
  if (!blockers.length) {
    return '--'
  }
  return blockers.map((item) => reasonLabel(item)).join('；')
}

function triggerReasonLabel(reason: string | null): string {
  const mapping: Record<string, string> = {
    golden_cross: '短均线上穿长均线',
    death_cross: '短均线下穿长均线',
    trend_follow_buy: '趋势延续并放大',
    trend_exit: '趋势走弱，先减仓',
    insufficient_history: '历史数据不足',
    history_unavailable: '历史行情不可用',
    macd_golden_cross_above_zero: 'MACD 零轴上金叉',
    macd_golden_cross_below_zero: 'MACD 零轴下金叉',
    macd_death_cross_below_zero: 'MACD 零轴下死叉',
    macd_death_cross_above_zero: 'MACD 零轴上死叉',
    macd_histogram_expanding: 'MACD 柱线扩张',
    macd_histogram_contracting: 'MACD 柱线收缩',
    macd_below_zero_weakening: 'MACD 零轴下走弱',
    macd_waiting: 'MACD 尚未形成有效信号',
    strategy_run_failed: '策略执行失败',
  }
  if (!reason) {
    return '--'
  }
  return mapping[reason] ?? reason
}

function recommendationLabel(value: boolean | null): string {
  if (value === null) {
    return '不适用'
  }
  return value ? '已确认' : '未确认'
}

function formatPrice(value: number | null): string {
  if (value === null || value === undefined) {
    return '--'
  }
  return `¥${value.toFixed(2)}`
}

function formatSuggestedPosition(value: number | null): string {
  if (value === null || value === undefined) {
    return '--'
  }
  return `${(value * 100).toFixed(0)}%`
}

function executionOutcomeLabel(result: StrategyRunResult): string {
  if (result.order_submitted) {
    return '通过闸门并已下单'
  }
  if (result.reason === 'signal_only_mode') {
    return '仅信号模式'
  }
  if (result.execution_blockers.includes('t_plus_one_restriction')) {
    return 'T+1 限制'
  }
  if (result.execution_blockers.some((item) => item.startsWith('recommendation_'))) {
    return '信号成立但未过推荐池'
  }
  if (
    result.execution_blockers.some((item) =>
      ['quantity_below_min_lot', 'insufficient_cash', 'single_position_limit_exceeded', 'total_exposure_limit_exceeded'].includes(item),
    )
  ) {
    return '信号成立但仓位不足'
  }
  if (result.reason === 'signal_hold') {
    return '信号未触发交易'
  }
  return result.execution_blockers.length ? '信号成立但未执行' : '已生成交易计划'
}

function formatParameters(parameters: StrategyItem['parameters']): string[] {
  const labels: Record<string, string> = {
    short_window: '短均线',
    long_window: '长均线',
    fast_period: '快线',
    slow_period: '慢线',
    signal_period: '信号线',
    position_pct: '仓位上限',
  }
  return Object.entries(parameters).map(([key, value]) => {
    if (key === 'position_pct') {
      return `${labels[key] ?? key}: ${(Number(value) * 100).toFixed(0)}%`
    }
    return `${labels[key] ?? key}: ${value}`
  })
}

function formatPositionPct(parameters: StrategyItem['parameters']): string {
  const raw = Number(parameters.position_pct ?? 0.1)
  return `仓位 ${(raw * 100).toFixed(0)}%`
}

function formatTime(timestamp: string | null): string {
  if (!timestamp) {
    return '尚未运行'
  }
  return new Date(timestamp).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}
</script>
