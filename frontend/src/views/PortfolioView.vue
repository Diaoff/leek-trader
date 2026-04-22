<template>
  <section class="flex flex-col gap-6">
    <div>
      <h2 class="text-2xl font-bold text-slate-900">交易与持仓</h2>
      <p class="text-slate-500">通过正式下单接口提交买入或卖出订单，并查看最近订单记录。</p>
    </div>

    <el-row :gutter="16">
      <el-col v-for="metric in metrics" :key="metric.label" :xs="24" :sm="12" :lg="6">
        <el-card shadow="hover">
          <div class="text-sm text-slate-500">{{ metric.label }}</div>
          <div class="mt-2 text-2xl font-bold text-slate-900">{{ metric.value }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :xs="24" :lg="10">
        <el-card>
          <template #header>
            <div class="font-semibold">下单</div>
          </template>

          <el-form label-position="top" @submit.prevent="submitOrder">
            <el-form-item label="交易方向">
              <el-select v-model="form.side" class="w-full">
                <el-option label="买入" value="buy" />
                <el-option label="卖出" value="sell" />
              </el-select>
            </el-form-item>

            <el-form-item label="股票代码">
              <el-input v-model="form.symbol" placeholder="例如 sh600519" />
            </el-form-item>

            <el-form-item label="订单类型">
              <el-select v-model="form.order_type" class="w-full">
                <el-option label="市价" value="market" />
                <el-option label="限价" value="limit" />
              </el-select>
            </el-form-item>

            <el-form-item label="数量">
              <el-input-number v-model="form.quantity" :min="100" :step="100" class="w-full" />
            </el-form-item>

            <el-form-item label="价格">
              <el-input-number v-model="form.price" :min="0.01" :step="0.01" :precision="2" class="w-full" />
            </el-form-item>

            <el-button type="primary" :loading="submitting" @click="submitOrder">
              {{ form.side === 'buy' ? '提交买单' : '提交卖单' }}
            </el-button>
          </el-form>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="14">
        <el-card>
          <template #header>
            <div class="flex items-center justify-between gap-4">
              <span class="font-semibold">最近订单</span>
              <div class="flex items-center gap-2">
                <el-button text @click="handleMatchPending">尝试撮合挂单</el-button>
                <el-button text @click="refreshData">刷新</el-button>
              </div>
            </div>
          </template>

          <el-table :data="orders" stripe>
            <el-table-column prop="symbol" label="代码" min-width="140" />
            <el-table-column prop="side" label="方向" min-width="100" />
            <el-table-column prop="order_type" label="类型" min-width="100" />
            <el-table-column prop="quantity" label="数量" min-width="100" />
            <el-table-column prop="filled_price" label="成交价" min-width="120" />
            <el-table-column prop="filled_quantity" label="成交数量" min-width="120" />
            <el-table-column prop="status" label="状态" min-width="120" />
            <el-table-column prop="reject_reason" label="失败原因" min-width="160" />
            <el-table-column label="操作" min-width="120">
              <template #default="scope">
                <el-button
                  v-if="scope.row.status === 'pending'"
                  text
                  type="danger"
                  @click="handleCancel(scope.row.id)"
                >
                  撤销
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-card>
      <template #header>
        <div class="font-semibold">当前持仓</div>
      </template>

      <el-table :data="positions" stripe>
        <el-table-column prop="symbol" label="代码" min-width="140" />
        <el-table-column prop="quantity" label="持仓数量" min-width="110" />
        <el-table-column prop="available_quantity" label="可卖数量" min-width="110" />
        <el-table-column prop="average_cost" label="成本价" min-width="120" />
        <el-table-column prop="last_price" label="最新价" min-width="120" />
        <el-table-column prop="unrealized_pnl" label="浮盈亏" min-width="120" />
        <el-table-column prop="realized_pnl" label="已实现盈亏" min-width="140" />
      </el-table>
    </el-card>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { cancelOrder, createOrder, fetchOrders, matchPendingOrders, type OrderItem } from '../api/orders'
import { fetchPortfolioSummary, type PortfolioSummary } from '../api/portfolio'
import { fetchPositions, type PositionItem } from '../api/positions'

const orders = ref<OrderItem[]>([])
const positions = ref<PositionItem[]>([])
const submitting = ref(false)
const summary = ref<PortfolioSummary>({
  total_equity: 0,
  available_cash: 0,
  market_value: 0,
  unrealized_pnl: 0,
})
const form = reactive({
  side: 'buy' as 'buy' | 'sell',
  symbol: 'sh600519',
  order_type: 'market' as const,
  quantity: 100,
  price: 100,
})

const metrics = computed(() => [
  { label: '总资产', value: formatCurrency(summary.value.total_equity) },
  { label: '可用资金', value: formatCurrency(summary.value.available_cash) },
  { label: '持仓市值', value: formatCurrency(summary.value.market_value) },
  { label: '浮动盈亏', value: formatCurrency(summary.value.unrealized_pnl) },
])

onMounted(refreshData)

async function refreshData(): Promise<void> {
  const [ordersData, summaryData, positionsData] = await Promise.all([
    fetchOrders(),
    fetchPortfolioSummary(),
    fetchPositions(),
  ])
  orders.value = ordersData
  summary.value = summaryData
  positions.value = positionsData
}

async function submitOrder(): Promise<void> {
  submitting.value = true
  try {
    const result = await createOrder({
      symbol: form.symbol,
      side: form.side,
      order_type: form.order_type,
      quantity: form.quantity,
      price: form.price,
    })
    const status = result.status as string | undefined
    if (status === 'rejected') {
      ElMessage.error(`下单失败：${String(result.rejection_reason ?? '未知原因')}`)
    } else {
      ElMessage.success(form.side === 'buy' ? '买单提交成功' : '卖单提交成功')
    }
    await refreshData()
  } catch (error) {
    ElMessage.error('下单失败')
    throw error
  } finally {
    submitting.value = false
  }
}

async function handleCancel(orderId: number): Promise<void> {
  const result = await cancelOrder(orderId)
  if (result.status === 'accepted') {
    ElMessage.success('撤单成功')
  } else {
    ElMessage.error(String(result.message ?? '撤单失败'))
  }
  await refreshData()
}

async function handleMatchPending(): Promise<void> {
  const result = await matchPendingOrders()
  ElMessage.success(`撮合完成，成交 ${String(result.matched_count ?? 0)} 笔挂单`)
  await refreshData()
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    maximumFractionDigits: 2,
  }).format(value)
}
</script>
