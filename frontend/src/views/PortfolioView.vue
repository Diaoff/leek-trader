<template>
  <section class="space-y-6">
    <div class="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
      <PageHeader
        title="交易与持仓"
        subtitle="统一处理买卖指令、挂单撮合、持仓监控和最新委托状态。"
      />
      <div class="token-row">
        <button class="secondary-button" type="button" :disabled="portfolioStore.loading" @click="reload">
          刷新数据
        </button>
        <button class="primary-button" type="button" :disabled="portfolioStore.loading" @click="handleMatchPending">
          撮合挂单
        </button>
      </div>
    </div>

    <ErrorAlert :message="portfolioStore.error || localError" type="error" />
    <SuccessAlert v-if="successMessage" :message="successMessage" @close="successMessage = ''" />

    <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <MetricCard label="总资产" :value="formatCurrency(portfolioStore.summary.total_equity)" hint="账户权益总额" />
      <MetricCard label="可用资金" :value="formatCurrency(portfolioStore.summary.available_cash)" hint="可用于新开仓的现金" />
      <MetricCard
        label="浮动盈亏"
        :value="formatCurrency(portfolioStore.summary.unrealized_pnl)"
        hint="当前持仓未实现盈亏"
        :emphasis-class="Number(portfolioStore.summary.unrealized_pnl) >= 0 ? 'value-rise' : 'value-fall'"
      />
      <MetricCard
        label="挂单数量"
        :value="portfolioStore.pendingCount"
        :hint="`全部委托 ${portfolioStore.orderCount} 笔`"
        emphasis-class=""
      />
    </div>

    <div class="grid gap-4 2xl:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)]">
      <div class="grid gap-4 xl:grid-cols-2">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3 class="panel-title">买入指令</h3>
              <p class="panel-subtitle">输入标的、同步报价，然后下发限价单。</p>
            </div>
          </div>

          <form class="space-y-4" @submit.prevent="submitBuy">
            <div>
              <label class="field-label" for="buy-symbol">股票代码</label>
              <div class="flex flex-col gap-3 sm:flex-row">
                <input
                  id="buy-symbol"
                  v-model.trim="buyForm.symbol"
                  class="field-input"
                  type="text"
                  placeholder="输入带交易所前缀的股票代码"
                />
                <button class="secondary-button sm:min-w-[112px]" type="button" @click="fillBuyQuote">
                  同步报价
                </button>
              </div>
              <div class="field-help">代码建议带市场前缀。价格将从 `/quotes` 自动填充。</div>
            </div>

            <div>
              <label class="field-label" for="buy-price">委托价格</label>
              <input id="buy-price" v-model.number="buyForm.price" class="field-input mono-data" type="number" min="0" step="0.01" />
            </div>

            <div>
              <label class="field-label" for="buy-quantity">委托数量</label>
              <input id="buy-quantity" v-model.number="buyForm.quantity" class="field-input mono-data" type="number" min="1" step="1" />
              <div class="mt-3 token-row">
                <button class="token-chip" type="button" @click="setBuyQuantity(100)">100 股</button>
                <button class="token-chip" type="button" @click="setBuyQuantity(500)">500 股</button>
                <button class="token-chip" type="button" @click="setBuyQuantity(1000)">1000 股</button>
                <button class="token-chip" type="button" @click="setBuyMax">最大可买</button>
              </div>
            </div>

            <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
              <div class="muted-text text-sm">预计成交金额</div>
              <div class="mt-2 text-3xl font-semibold tracking-[-0.04em]">{{ formatCurrency(buyEstimate) }}</div>
              <div class="mt-2 text-sm text-[var(--text-tertiary)]">
                资金可用 {{ formatCurrency(portfolioStore.summary.available_cash) }}
              </div>
            </div>

            <button class="primary-button w-full" type="submit" :disabled="!canBuy || portfolioStore.loading">
              提交买入委托
            </button>
          </form>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div>
              <h3 class="panel-title">卖出指令</h3>
              <p class="panel-subtitle">从当前持仓直接选股，按可用数量发起卖单。</p>
            </div>
          </div>

          <form class="space-y-4" @submit.prevent="submitSell">
            <div>
              <label class="field-label" for="sell-symbol">持仓标的</label>
              <select id="sell-symbol" v-model="sellForm.symbol" class="field-select" @change="syncSellPosition">
                <option value="">请选择持仓</option>
                <option v-for="position in portfolioStore.positions" :key="position.symbol" :value="position.symbol">
                  {{ securityLabel(position) }} · 可卖 {{ position.available_quantity }} 股
                </option>
              </select>
            </div>

            <div>
              <label class="field-label" for="sell-price">委托价格</label>
              <input id="sell-price" v-model.number="sellForm.price" class="field-input mono-data" type="number" min="0" step="0.01" />
            </div>

            <div>
              <label class="field-label" for="sell-quantity">委托数量</label>
              <input id="sell-quantity" v-model.number="sellForm.quantity" class="field-input mono-data" type="number" min="1" step="1" />
              <div class="mt-3 token-row">
                <button class="token-chip" type="button" @click="setSellRatio(0.25)">25%</button>
                <button class="token-chip" type="button" @click="setSellRatio(0.5)">50%</button>
                <button class="token-chip" type="button" @click="setSellRatio(0.75)">75%</button>
                <button class="token-chip" type="button" @click="setSellRatio(1)">全部</button>
              </div>
            </div>

            <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
              <div class="muted-text text-sm">预计回收资金</div>
              <div class="mt-2 text-3xl font-semibold tracking-[-0.04em]">{{ formatCurrency(sellEstimate) }}</div>
              <div class="mt-2 text-sm text-[var(--text-tertiary)]">
                {{ selectedSellPosition ? `可卖 ${selectedSellPosition.available_quantity} 股` : '请选择有效持仓' }}
              </div>
            </div>

            <button class="danger-button w-full" type="submit" :disabled="!canSell || portfolioStore.loading">
              提交卖出委托
            </button>
          </form>
        </div>
      </div>

      <div class="panel space-y-4">
        <div>
          <div class="section-label">Execution Queue</div>
          <h3 class="panel-title mt-3">委托队列状态</h3>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
            <div class="muted-text text-sm">挂单中</div>
            <div class="mt-2 text-3xl font-semibold tracking-[-0.04em]">{{ portfolioStore.pendingCount }}</div>
          </div>
          <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
            <div class="muted-text text-sm">持仓标的</div>
            <div class="mt-2 text-3xl font-semibold tracking-[-0.04em]">{{ portfolioStore.positionCount }}</div>
          </div>
        </div>

        <div class="rounded-[20px] border border-white/5 bg-white/[0.03] p-4">
          <div class="panel-subtitle !mt-0">最新待处理挂单</div>
          <div v-if="portfolioStore.pendingOrders.length === 0" class="mt-3 text-sm text-[var(--text-tertiary)]">
            当前没有待撮合的挂单。
          </div>
          <div v-else class="mt-3 space-y-3">
            <div
              v-for="order in portfolioStore.pendingOrders.slice(0, 5)"
              :key="order.id"
              class="flex items-center justify-between rounded-2xl border border-white/5 px-4 py-3"
            >
              <div>
                <div class="font-semibold">{{ securityLabel(order) }}</div>
                <div class="text-xs text-[var(--text-tertiary)]">#{{ order.id }} · {{ order.side === 'buy' ? '买入' : '卖出' }}</div>
              </div>
              <div class="text-right">
                <div class="mono-data">{{ order.quantity }} 股</div>
                <div class="text-xs text-[var(--text-tertiary)]">{{ formatCurrency(order.price) }}</div>
              </div>
            </div>
          </div>
        </div>

        <div class="rounded-[20px] border border-white/5 bg-white/[0.03] p-4 text-sm text-[var(--text-secondary)]">
          撮合按钮会调用 `/orders/match-pending`，适合在手动验收交易闭环时快速推进状态。
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <div>
          <h3 class="panel-title">当前持仓</h3>
          <p class="panel-subtitle">以持仓成本、最新价和浮动盈亏判断仓位质量。</p>
        </div>
      </div>

      <div v-if="portfolioStore.positions.length === 0" class="empty-state">
        <div>当前没有持仓</div>
        <div class="text-sm text-[var(--text-tertiary)]">先从上方交易面板提交买入委托。</div>
      </div>
      <div v-else class="table-shell">
        <table class="data-table">
          <thead>
            <tr>
              <th>标的</th>
              <th>持仓数量</th>
              <th>可卖数量</th>
              <th>成本价</th>
              <th>最新价</th>
              <th>止损价</th>
              <th>止盈价</th>
              <th>保护状态</th>
              <th>补仓次数</th>
              <th>最近触发</th>
              <th>浮动盈亏</th>
              <th>仓位占比</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="position in portfolioStore.positions" :key="position.id">
              <td>
                <div class="font-semibold">{{ securityLabel(position) }}</div>
                <div class="mono-data muted-text mt-1">{{ position.market }}</div>
              </td>
              <td class="mono-data">{{ position.quantity }}</td>
              <td class="mono-data">{{ position.available_quantity }}</td>
              <td class="mono-data">{{ formatCurrency(position.average_cost) }}</td>
              <td class="mono-data">{{ formatCurrency(position.last_price) }}</td>
              <td class="mono-data">{{ formatNullableCurrency(position.stop_loss_price) }}</td>
              <td class="mono-data">{{ formatNullableCurrency(position.take_profit_price) }}</td>
              <td>{{ guardStatusLabel(position.exit_guard_status) }}</td>
              <td class="mono-data">{{ position.strategy_add_count }}</td>
              <td>{{ latestTriggerLabel(position) }}</td>
              <td :class="['mono-data font-semibold', Number(position.unrealized_pnl) >= 0 ? 'value-rise' : 'value-fall']">
                {{ formatCurrency(position.unrealized_pnl) }}
              </td>
              <td class="mono-data">{{ positionWeight(position) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <div>
          <h3 class="panel-title">委托列表</h3>
          <p class="panel-subtitle">只保留当前 API 提供的字段，避免再依赖不存在的 `created_at`。</p>
        </div>
      </div>

      <div v-if="portfolioStore.orders.length === 0" class="empty-state">
        <div>暂无委托记录</div>
      </div>
      <div v-else class="table-shell">
        <table class="data-table">
          <thead>
            <tr>
              <th>订单</th>
              <th>方向</th>
              <th>类型</th>
              <th>状态</th>
              <th>拒绝原因</th>
              <th>委托价格</th>
              <th>数量</th>
              <th>成交价格</th>
              <th>成交数量</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="order in portfolioStore.orders" :key="order.id">
              <td>
                <div class="font-semibold">{{ securityLabel(order) }}</div>
                <div class="mono-data muted-text mt-1">#{{ order.id }}</div>
              </td>
              <td :class="order.side === 'buy' ? 'value-positive' : 'value-negative'">
                {{ order.side === 'buy' ? '买入' : '卖出' }}
              </td>
              <td class="mono-data uppercase">{{ order.order_type }}</td>
              <td>
                <span :class="['status-chip', statusTone(order.status)]">{{ statusLabel(order.status) }}</span>
              </td>
              <td class="text-sm text-[var(--text-secondary)]">
                {{ order.reject_reason ?? '--' }}
              </td>
              <td class="mono-data">{{ formatCurrency(order.price) }}</td>
              <td class="mono-data">{{ order.quantity }}</td>
              <td class="mono-data">{{ formatCurrency(order.filled_price) }}</td>
              <td class="mono-data">{{ order.filled_quantity }}</td>
              <td>
                <button
                  v-if="order.status === 'pending'"
                  class="danger-button !min-h-9 px-3 text-xs"
                  type="button"
                  @click="handleCancel(order.id)"
                >
                  撤单
                </button>
                <span v-else class="muted-text text-sm">已完成</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'

import { fetchQuotes } from '../api/quotes'
import type { PositionItem } from '../types/position'
import ErrorAlert from '../components/ErrorAlert.vue'
import MetricCard from '../components/MetricCard.vue'
import PageHeader from '../components/PageHeader.vue'
import SuccessAlert from '../components/SuccessAlert.vue'
import { usePortfolioStore } from '../stores/portfolio'
import { formatCurrency } from '../utils/format'
import { formatSecurityDisplay, type SecurityDisplaySource } from '../utils/securityDisplay'

const portfolioStore = usePortfolioStore()

const localError = ref('')
const successMessage = ref('')

const buyForm = reactive({
  symbol: '',
  quantity: 100,
  price: 0,
})

const sellForm = reactive({
  symbol: '',
  quantity: 0,
  price: 0,
})

const selectedSellPosition = computed(() =>
  portfolioStore.positions.find((position) => position.symbol === sellForm.symbol) ?? null,
)

const buyEstimate = computed(() => Math.max(0, buyForm.quantity) * Math.max(0, buyForm.price))
const sellEstimate = computed(() => Math.max(0, sellForm.quantity) * Math.max(0, sellForm.price))

function securityLabel(item: SecurityDisplaySource | string | null | undefined): string {
  return formatSecurityDisplay(item)
}

const canBuy = computed(
  () =>
    buyForm.symbol.trim().length > 0 &&
    buyForm.quantity > 0 &&
    buyForm.price > 0 &&
    buyEstimate.value <= portfolioStore.summary.available_cash,
)

const canSell = computed(
  () =>
    sellForm.symbol.trim().length > 0 &&
    sellForm.quantity > 0 &&
    sellForm.price > 0 &&
    !!selectedSellPosition.value &&
    sellForm.quantity <= selectedSellPosition.value.available_quantity,
)

function statusLabel(status: string): string {
  const mapping: Record<string, string> = {
    pending: '待成交',
    filled: '已成交',
    rejected: '已拒绝',
    cancelled: '已撤单',
  }
  return mapping[status] ?? status
}

function statusTone(status: string): 'positive' | 'negative' | 'neutral' {
  if (status === 'filled') {
    return 'positive'
  }
  if (status === 'rejected' || status === 'cancelled') {
    return 'negative'
  }
  return 'neutral'
}

function positionWeight(position: PositionItem): string {
  const marketValue = Number(position.last_price) * position.quantity
  if (portfolioStore.summary.market_value <= 0) {
    return '0.00%'
  }
  return `${((marketValue / portfolioStore.summary.market_value) * 100).toFixed(2)}%`
}

function formatNullableCurrency(value: string | null): string {
  return value ? formatCurrency(value) : '--'
}

function guardStatusLabel(status: PositionItem['exit_guard_status']): string {
  const mapping: Record<PositionItem['exit_guard_status'], string> = {
    inactive: '未启用',
    active: '保护中',
    triggered: '已触发',
  }
  return mapping[status] ?? status
}

function latestTriggerLabel(position: PositionItem): string {
  if (!position.exit_trigger_reason) {
    return '--'
  }
  const reasonLabel = position.exit_trigger_reason === 'stop_loss' ? '止损' : '止盈'
  if (!position.exit_triggered_at) {
    return reasonLabel
  }
  const timestamp = new Date(position.exit_triggered_at)
  if (Number.isNaN(timestamp.getTime())) {
    return reasonLabel
  }
  return `${reasonLabel} · ${timestamp.toLocaleString('zh-CN', { hour12: false })}`
}

async function reload(): Promise<void> {
  localError.value = ''
  try {
    await portfolioStore.loadAllPortfolioData()
  } catch (err: unknown) {
    localError.value = err instanceof Error ? err.message : '交易数据加载失败'
  }
}

async function syncQuote(symbol: string): Promise<number | null> {
  const normalized = symbol.trim()
  if (!normalized) {
    return null
  }

  try {
    const [quote] = await fetchQuotes([normalized])
    return quote?.price ?? null
  } catch (err: unknown) {
    localError.value = err instanceof Error ? err.message : '报价同步失败'
    return null
  }
}

async function fillBuyQuote(): Promise<void> {
  const price = await syncQuote(buyForm.symbol)
  if (typeof price === 'number') {
    buyForm.price = Number(price.toFixed(2))
  }
}

function syncSellPosition(): void {
  if (!selectedSellPosition.value) {
    sellForm.price = 0
    sellForm.quantity = 0
    return
  }

  sellForm.price = Number(Number(selectedSellPosition.value.last_price).toFixed(2))
  sellForm.quantity = Math.min(selectedSellPosition.value.available_quantity, sellForm.quantity || selectedSellPosition.value.available_quantity)
}

function setBuyQuantity(quantity: number): void {
  buyForm.quantity = quantity
}

function setBuyMax(): void {
  if (buyForm.price <= 0) {
    return
  }

  buyForm.quantity = Math.floor(portfolioStore.summary.available_cash / buyForm.price)
}

function setSellRatio(ratio: number): void {
  if (!selectedSellPosition.value) {
    return
  }

  sellForm.quantity = Math.max(1, Math.floor(selectedSellPosition.value.available_quantity * ratio))
}

async function submitBuy(): Promise<void> {
  localError.value = ''
  successMessage.value = ''

  try {
    await portfolioStore.submitOrder({
      symbol: buyForm.symbol.trim(),
      side: 'buy',
      order_type: 'limit',
      quantity: buyForm.quantity,
      price: buyForm.price,
    })
    successMessage.value = `已提交买入委托：${securityLabel(buyForm.symbol.trim())}`
    buyForm.quantity = 100
  } catch (err: unknown) {
    localError.value = err instanceof Error ? err.message : '买入委托提交失败'
  }
}

async function submitSell(): Promise<void> {
  localError.value = ''
  successMessage.value = ''

  try {
    await portfolioStore.submitOrder({
      symbol: sellForm.symbol.trim(),
      side: 'sell',
      order_type: 'limit',
      quantity: sellForm.quantity,
      price: sellForm.price,
    })
    successMessage.value = `已提交卖出委托：${securityLabel(selectedSellPosition.value ?? sellForm.symbol.trim())}`
  } catch (err: unknown) {
    localError.value = err instanceof Error ? err.message : '卖出委托提交失败'
  }
}

async function handleCancel(orderId: number): Promise<void> {
  localError.value = ''
  successMessage.value = ''

  try {
    await portfolioStore.cancelOrder(orderId)
    successMessage.value = `订单 #${orderId} 已撤单`
  } catch (err: unknown) {
    localError.value = err instanceof Error ? err.message : '撤单失败'
  }
}

async function handleMatchPending(): Promise<void> {
  localError.value = ''
  successMessage.value = ''

  try {
    const result = await portfolioStore.matchPendingOrders()
    successMessage.value = `撮合完成，本次成交 ${result.matched_count} 笔挂单`
  } catch (err: unknown) {
    localError.value = err instanceof Error ? err.message : '挂单撮合失败'
  }
}

void reload()
</script>
