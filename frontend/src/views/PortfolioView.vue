<template>
  <section class="flex flex-col gap-6">
    <div>
      <h2 class="page-title">交易与持仓</h2>
      <p class="page-subtitle">这是当前 MVP 的核心页面：下单、挂单撮合、订单跟踪、持仓和账户摘要都在这里闭环。</p>
    </div>

    <el-alert
      v-if="errorMessage"
      :closable="false"
      :title="errorMessage"
      type="warning"
      show-icon
    />
    <el-alert
      v-if="actionMessage"
      :closable="false"
      :title="actionMessage"
      :type="actionType"
      show-icon
    />

    <div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
      <el-card v-for="metric in metrics" :key="metric.label" class="surface-card metric-card">
        <div class="metric-label">{{ metric.label }}</div>
        <div class="metric-value" :class="metric.emphasisClass">{{ metric.value }}</div>
        <div class="metric-hint">{{ metric.hint }}</div>
      </el-card>
    </div>

    <div class="grid grid-cols-1 gap-4 xl:grid-cols-[360px_1fr]">
      <el-card class="surface-card">
        <template #header>
          <div class="font-semibold">提交订单</div>
        </template>

        <el-form label-position="top" @submit.prevent="submitOrder">
          <el-form-item label="交易方向">
            <el-segmented
              v-model="form.side"
              :options="[
                { label: '买入', value: 'buy' },
                { label: '卖出', value: 'sell' },
              ]"
              block
            />
          </el-form-item>

          <el-form-item label="股票代码">
            <el-input v-model="form.symbol" placeholder="例如 sh600519" />
          </el-form-item>

          <el-form-item label="订单类型">
            <el-select v-model="form.order_type" class="w-full">
              <el-option label="市价单" value="market" />
              <el-option label="限价单" value="limit" />
            </el-select>
          </el-form-item>

          <el-form-item label="数量">
            <el-input-number v-model="form.quantity" :min="100" :step="100" class="w-full" />
          </el-form-item>

          <el-form-item label="价格">
            <el-input-number v-model="form.price" :min="0.01" :step="0.01" :precision="2" class="w-full" />
          </el-form-item>

          <el-button class="w-full" type="primary" :loading="submitting" @click="submitOrder">
            {{ form.order_type === 'limit' ? '创建挂单' : '提交市价单' }}
          </el-button>
        </el-form>
      </el-card>

      <el-card class="surface-card">
        <template #header>
          <div class="flex items-center justify-between gap-4">
            <span class="font-semibold">订单列表</span>
            <div class="flex items-center gap-2">
              <el-button text :loading="refreshing" @click="handleMatchPending">尝试撮合挂单</el-button>
              <el-button text :loading="refreshing" @click="refreshData">刷新</el-button>
            </div>
          </div>
        </template>

        <el-table v-loading="refreshing" :data="orders" stripe empty-text="暂无订单">
          <el-table-column prop="symbol" label="代码" min-width="130" />
          <el-table-column label="方向" min-width="90">
            <template #default="{ row }">
              <el-tag class="pill-tag" :type="row.side === 'buy' ? 'danger' : 'success'">
                {{ row.side === 'buy' ? '买入' : '卖出' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="类型" min-width="90">
            <template #default="{ row }">{{ row.order_type === 'market' ? '市价' : '限价' }}</template>
          </el-table-column>
          <el-table-column prop="quantity" label="委托数量" min-width="100" />
          <el-table-column label="成交价" min-width="110">
            <template #default="{ row }">{{ formatCurrency(row.filled_price) }}</template>
          </el-table-column>
          <el-table-column prop="filled_quantity" label="成交数量" min-width="100" />
          <el-table-column label="状态" min-width="110">
            <template #default="{ row }">
              <el-tag class="pill-tag" :type="statusTagType(row.status)">
                {{ statusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="reject_reason" label="失败原因" min-width="160" />
          <el-table-column label="操作" min-width="110" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.status === 'pending'"
                text
                type="danger"
                @click="handleCancel(row.id)"
              >
                撤单
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <el-card class="surface-card">
      <template #header>
        <div class="font-semibold">当前持仓</div>
      </template>

      <el-table v-loading="refreshing" :data="positions" stripe empty-text="暂无持仓">
        <el-table-column prop="symbol" label="代码" min-width="130" />
        <el-table-column prop="quantity" label="持仓数量" min-width="100" />
        <el-table-column prop="available_quantity" label="可卖数量" min-width="100" />
        <el-table-column label="成本价" min-width="120">
          <template #default="{ row }">{{ formatCurrency(row.average_cost) }}</template>
        </el-table-column>
        <el-table-column label="最新价" min-width="120">
          <template #default="{ row }">{{ formatCurrency(row.last_price) }}</template>
        </el-table-column>
        <el-table-column label="浮盈亏" min-width="130">
          <template #default="{ row }">
            <span :class="Number(row.unrealized_pnl) >= 0 ? 'text-emerald-600' : 'text-rose-600'">
              {{ formatCurrency(row.unrealized_pnl) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="已实现盈亏" min-width="140">
          <template #default="{ row }">
            <span :class="Number(row.realized_pnl) >= 0 ? 'text-emerald-600' : 'text-rose-600'">
              {{ formatCurrency(row.realized_pnl) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  cancelOrder,
  createOrder,
  fetchOrders,
  matchPendingOrders,
  type OrderItem,
} from '../api/orders'
import { fetchPortfolioSummary, type PortfolioSummary } from '../api/portfolio'
import { fetchPositions, type PositionItem } from '../api/positions'
import { formatCurrency } from '../utils/format'
import { getApiErrorMessage } from '../utils/http'

const orders = ref<OrderItem[]>([])
const positions = ref<PositionItem[]>([])
const submitting = ref(false)
const refreshing = ref(false)
const errorMessage = ref('')
const actionMessage = ref('')
const actionType = ref<'success' | 'warning'>('success')
const summary = ref<PortfolioSummary>({
  total_equity: 0,
  available_cash: 0,
  frozen_cash: 0,
  market_value: 0,
  unrealized_pnl: 0,
})
const form = reactive({
  side: 'buy' as 'buy' | 'sell',
  symbol: 'sh600519',
  order_type: 'market' as 'market' | 'limit',
  quantity: 100,
  price: 100,
})

const metrics = computed(() => [
  {
    label: '总资产',
    value: formatCurrency(summary.value.total_equity),
    hint: '默认账户当前总权益',
    emphasisClass: '',
  },
  {
    label: '可用资金',
    value: formatCurrency(summary.value.available_cash),
    hint: `冻结 ${formatCurrency(summary.value.frozen_cash)}`,
    emphasisClass: '',
  },
  {
    label: '持仓市值',
    value: formatCurrency(summary.value.market_value),
    hint: `${positions.value.length} 只持仓`,
    emphasisClass: '',
  },
  {
    label: '浮动盈亏',
    value: formatCurrency(summary.value.unrealized_pnl),
    hint: '按最新行情估值',
    emphasisClass: summary.value.unrealized_pnl >= 0 ? 'text-emerald-700' : 'text-rose-700',
  },
  {
    label: '挂单数量',
    value: String(orders.value.filter((item) => item.status === 'pending').length),
    hint: '支持手动触发撮合',
    emphasisClass: '',
  },
])

onMounted(() => {
  void refreshData()
})

async function refreshData(): Promise<void> {
  refreshing.value = true
  errorMessage.value = ''

  try {
    const [ordersData, summaryData, positionsData] = await Promise.all([
      fetchOrders(),
      fetchPortfolioSummary(),
      fetchPositions(),
    ])
    orders.value = ordersData
    summary.value = summaryData
    positions.value = positionsData
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error, '交易数据刷新失败')
  } finally {
    refreshing.value = false
  }
}

async function submitOrder(): Promise<void> {
  submitting.value = true
  errorMessage.value = ''
  actionMessage.value = ''

  try {
    const result = await createOrder({
      symbol: form.symbol.trim(),
      side: form.side,
      order_type: form.order_type,
      quantity: form.quantity,
      price: form.price,
    })

    if (result.status === 'rejected') {
      actionType.value = 'warning'
      actionMessage.value = `下单失败：${result.rejection_reason ?? '未知原因'}`
      ElMessage.warning(actionMessage.value)
    } else if (result.order?.status === 'pending') {
      actionType.value = 'success'
      actionMessage.value = '挂单已创建，可继续手动触发撮合或撤单。'
      ElMessage.success(actionMessage.value)
    } else {
      actionType.value = 'success'
      actionMessage.value = '订单已提交并完成处理。'
      ElMessage.success(actionMessage.value)
    }

    await refreshData()
  } catch (error) {
    const message = getApiErrorMessage(error, '下单失败')
    actionType.value = 'warning'
    actionMessage.value = message
    ElMessage.error(message)
  } finally {
    submitting.value = false
  }
}

async function handleCancel(orderId: number): Promise<void> {
  try {
    const result = await cancelOrder(orderId)
    if (result.status === 'accepted') {
      ElMessage.success('撤单成功')
      actionType.value = 'success'
      actionMessage.value = '挂单已撤销。'
    } else {
      const message = result.message ?? '撤单失败'
      ElMessage.warning(message)
      actionType.value = 'warning'
      actionMessage.value = message
    }
    await refreshData()
  } catch (error) {
    const message = getApiErrorMessage(error, '撤单失败')
    ElMessage.error(message)
    actionType.value = 'warning'
    actionMessage.value = message
  }
}

async function handleMatchPending(): Promise<void> {
  try {
    const result = await matchPendingOrders()
    actionType.value = 'success'
    actionMessage.value = `撮合完成，本次成交 ${result.matched_count} 笔挂单。`
    ElMessage.success(actionMessage.value)
    await refreshData()
  } catch (error) {
    const message = getApiErrorMessage(error, '挂单撮合失败')
    actionType.value = 'warning'
    actionMessage.value = message
    ElMessage.error(message)
  }
}

function statusLabel(status: OrderItem['status']): string {
  const mapping: Record<OrderItem['status'], string> = {
    pending: '挂单中',
    filled: '已成交',
    rejected: '已拒绝',
    cancelled: '已撤销',
  }
  return mapping[status]
}

function statusTagType(status: OrderItem['status']): 'info' | 'success' | 'warning' | 'danger' {
  if (status === 'filled') {
    return 'success'
  }
  if (status === 'pending') {
    return 'warning'
  }
  if (status === 'cancelled') {
    return 'info'
  }
  return 'danger'
}
</script>
