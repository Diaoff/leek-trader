<template>
  <section class="flex flex-col gap-6">
    <PageHeader
      title="交易与持仓"
      subtitle="这是当前 MVP 的核心页面：下单、挂单撮合、订单跟踪、持仓和账户摘要都在这里闭环。"
    />

    <ErrorAlert :message="orderError || portfolioError" />

    <SuccessAlert v-if="successMessage" :message="successMessage" @close="successMessage = ''" />

    <div class="grid grid-cols-1 gap-4 md:grid-cols-3">
      <div class="card p-5 relative sharp-card">
        <h3 class="text-sm text-gray-400 font-medium mb-2">总市值</h3>
        <p class="text-3xl font-bold">{{ formatCurrency(portfolioStore.summary.total_equity) }}</p>
      </div>
      <div class="card p-5 relative sharp-card">
        <h3 class="text-sm text-gray-400 font-medium mb-2">总盈亏</h3>
        <p class="text-3xl font-bold text-green-400">+{{ formatCurrency(portfolioStore.summary.unrealized_pnl) }}</p>
      </div>
      <div class="card p-5 relative sharp-card">
        <h3 class="text-sm text-gray-400 font-medium mb-2">持仓收益率</h3>
        <p class="text-3xl font-bold text-green-400">+{{ calculateProfitRate }}%</p>
      </div>
    </div>

    <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <!-- Buy Form -->
      <el-card class="surface-card">
        <div class="flex items-center justify-between mb-5">
          <h3 class="text-lg font-medium">买入</h3>
          <span class="text-sm text-gray-400">可用资金: {{ formatCurrency(portfolioStore.summary.available_cash) }}</span>
        </div>
        <form class="space-y-4" @submit.prevent="submitOrder">
          <div>
            <label class="block text-sm text-gray-400 mb-2">股票代码</label>
            <input 
              type="text" 
              class="w-full bg-dark-secondary border border-dark-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded-none" 
              placeholder="输入股票代码"
              v-model="buyForm.stockCode"
              @input="searchStock"
            >
          </div>
          <div v-if="selectedStock">
            <label class="block text-sm text-gray-400 mb-2">股票名称</label>
            <input type="text" class="w-full bg-dark-secondary border border-dark-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded-none" readonly :value="selectedStock.name">
          </div>
          <div v-if="selectedStock">
            <label class="block text-sm text-gray-400 mb-2">最新价</label>
            <input type="text" class="w-full bg-dark-secondary border border-dark-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded-none" readonly :value="selectedStock.price">
          </div>
          <div>
            <label class="block text-sm text-gray-400 mb-2">买入数量</label>
            <input 
              type="number" 
              class="w-full bg-dark-secondary border border-dark-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded-none" 
              placeholder="输入买入数量"
              v-model.number="buyForm.quantity"
              @input="calculateBuyAmount"
            >
            <div class="flex justify-between mt-2">
              <button type="button" class="px-3 py-1 text-sm bg-dark-secondary hover:bg-dark-card border border-dark-border sharp-btn" @click="setBuyQuantity(100)">100股</button>
              <button type="button" class="px-3 py-1 text-sm bg-dark-secondary hover:bg-dark-card border border-dark-border sharp-btn" @click="setBuyQuantity(500)">500股</button>
              <button type="button" class="px-3 py-1 text-sm bg-dark-secondary hover:bg-dark-card border border-dark-border sharp-btn" @click="setBuyQuantity(1000)">1000股</button>
              <button type="button" class="px-3 py-1 text-sm bg-dark-secondary hover:bg-dark-card border border-dark-border sharp-btn" @click="setBuyMax">最大</button>
            </div>
          </div>
          <div>
            <label class="block text-sm text-gray-400 mb-2">预估金额</label>
            <input type="text" class="w-full bg-dark-secondary border border-dark-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded-none" readonly :value="`${formatCurrency(buyForm.amount)}`">
          </div>
          <button type="submit" class="w-full bg-blue-600 text-white py-2 sharp-btn" :disabled="!canBuy">确认买入</button>
        </form>
      </el-card>

      <!-- Sell Form -->
      <el-card class="surface-card">
        <div class="flex items-center justify-between mb-5">
          <h3 class="text-lg font-medium">卖出</h3>
          <span class="text-sm text-gray-400">持仓市值: {{ formatCurrency(portfolioStore.summary.market_value) }}</span>
        </div>
        <form class="space-y-4" @submit.prevent="submitOrder">
          <div>
            <label class="block text-sm text-gray-400 mb-2">选择股票</label>
            <select class="w-full bg-dark-secondary border border-dark-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded-none" v-model="sellForm.stockCode" @change="onSellStockChange">
              <option value="">请选择要卖出的股票</option>
              <option v-for="position in portfolioStore.positions" :key="position.symbol" :value="position.symbol">
                {{ position.symbol }} - {{ position.quantity }}股
              </option>
            </select>
          </div>
          <div v-if="selectedSellStock">
            <label class="block text-sm text-gray-400 mb-2">最新价</label>
            <input type="text" class="w-full bg-dark-secondary border border-dark-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded-none" readonly :value="selectedSellStock.price">
          </div>
          <div v-if="selectedSellStock">
            <label class="block text-sm text-gray-400 mb-2">可用数量</label>
            <input type="text" class="w-full bg-dark-secondary border border-dark-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded-none" readonly :value="selectedSellStock.quantity">
          </div>
          <div>
            <label class="block text-sm text-gray-400 mb-2">卖出数量</label>
            <input 
              type="number" 
              class="w-full bg-dark-secondary border border-dark-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded-none" 
              placeholder="输入卖出数量"
              v-model.number="sellForm.quantity"
              @input="calculateSellAmount"
            >
            <div class="flex justify-between mt-2">
              <button type="button" class="px-3 py-1 text-sm bg-dark-secondary hover:bg-dark-card border border-dark-border sharp-btn" @click="setSellPercentage(0.25)">25%</button>
              <button type="button" class="px-3 py-1 text-sm bg-dark-secondary hover:bg-dark-card border border-dark-border sharp-btn" @click="setSellPercentage(0.5)">50%</button>
              <button type="button" class="px-3 py-1 text-sm bg-dark-secondary hover:bg-dark-card border border-dark-border sharp-btn" @click="setSellPercentage(0.75)">75%</button>
              <button type="button" class="px-3 py-1 text-sm bg-dark-secondary hover:bg-dark-card border border-dark-border sharp-btn" @click="setSellAll">全部</button>
            </div>
          </div>
          <div>
            <label class="block text-sm text-gray-400 mb-2">预估金额</label>
            <input type="text" class="w-full bg-dark-secondary border border-dark-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded-none" readonly :value="`${formatCurrency(sellForm.amount)}`">
          </div>
          <button type="submit" class="w-full bg-red-600 text-white py-2 sharp-btn" :disabled="!canSell">确认卖出</button>
        </form>
      </el-card>
    </div>

    <!-- Positions -->
    <div class="card p-5">
      <div class="flex justify-between items-center mb-5">
        <h3 class="text-lg font-medium">当前持仓</h3>
        <div class="flex space-x-3">
          <button class="bg-dark-secondary border border-dark-border px-3 py-2 hover:bg-dark-card transition-colors sharp-btn">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            导出
          </button>
        </div>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-dark-border">
              <th class="text-left py-3 px-2 text-sm font-medium text-gray-400">股票名称</th>
              <th class="text-right py-3 px-2 text-sm font-medium text-gray-400">持仓数量</th>
              <th class="text-right py-3 px-2 text-sm font-medium text-gray-400">成本价</th>
              <th class="text-right py-3 px-2 text-sm font-medium text-gray-400">现价</th>
              <th class="text-right py-3 px-2 text-sm font-medium text-gray-400">盈亏额</th>
              <th class="text-right py-3 px-2 text-sm font-medium text-gray-400">盈亏率</th>
              <th class="text-right py-3 px-2 text-sm font-medium text-gray-400">市值占比</th>
              <th class="text-right py-3 px-2 text-sm font-medium text-gray-400">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr class="border-b border-dark-border hover:bg-dark-secondary/50" v-for="position in portfolioStore.positions" :key="position.symbol">
              <td class="py-3 px-2">
                <div>
                  <div class="font-medium">{{ position.symbol }}</div>
                </div>
              </td>
              <td class="text-right py-3 px-2">{{ position.quantity }}</td>
              <td class="text-right py-3 px-2">{{ formatCurrency(position.average_cost) }}</td>
              <td class="text-right py-3 px-2 font-medium">{{ formatCurrency(position.last_price) }}</td>
              <td class="text-right py-3 px-2" :class="Number(position.unrealized_pnl) >= 0 ? 'text-green-400' : 'text-red-400'">
                {{ Number(position.unrealized_pnl) >= 0 ? '+' : '' }}{{ formatCurrency(position.unrealized_pnl) }}
              </td>
              <td class="text-right py-3 px-2" :class="Number(position.unrealized_pnl) >= 0 ? 'text-green-400' : 'text-red-400'">
                {{ calculatePositionProfitRate(position) }}%
              </td>
              <td class="text-right py-3 px-2">{{ calculateValueRatio(position) }}%</td>
              <td class="text-right py-3 px-2">
                <button class="text-red-400 hover:text-red-300 mr-3" @click="quickSell(position)">
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
                <button class="text-yellow-400 hover:text-yellow-300" @click="viewPositionDetail(position)">
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                  </svg>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Today's Orders -->
    <div class="card p-5">
      <h3 class="text-lg font-medium mb-5">当日委托</h3>
      <div class="flex border-b border-dark-border mb-5">
        <button class="px-4 py-2 text-blue-400 border-b-2 border-blue-400">全部</button>
        <button class="px-4 py-2 text-gray-400 hover:text-white">买入</button>
        <button class="px-4 py-2 text-gray-400 hover:text-white">卖出</button>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-dark-border">
              <th class="text-left py-3 px-2 text-sm font-medium text-gray-400">时间</th>
              <th class="text-left py-3 px-2 text-sm font-medium text-gray-400">股票</th>
              <th class="text-right py-3 px-2 text-sm font-medium text-gray-400">方向</th>
              <th class="text-right py-3 px-2 text-sm font-medium text-gray-400">委托价</th>
              <th class="text-right py-3 px-2 text-sm font-medium text-gray-400">委托量</th>
              <th class="text-right py-3 px-2 text-sm font-medium text-gray-400">状态</th>
              <th class="text-right py-3 px-2 text-sm font-medium text-gray-400">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr class="border-b border-dark-border hover:bg-dark-secondary/50" v-for="order in portfolioStore.orders" :key="order.id">
              <td class="py-3 px-2">{{ formatDateTime(order.created_at) }}</td>
              <td class="py-3 px-2">{{ order.symbol }}</td>
              <td class="text-right py-3 px-2">
                <span :class="order.side === 'buy' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'" class="text-xs px-2 py-1 border border-current">
                  {{ order.side === 'buy' ? '买入' : '卖出' }}
                </span>
              </td>
              <td class="text-right py-3 px-2">{{ formatCurrency(order.price) }}</td>
              <td class="text-right py-3 px-2">{{ order.quantity }}</td>
              <td class="text-right py-3 px-2">
                <span :class="order.status === 'filled' ? 'bg-blue-500/20 text-blue-400' : order.status === 'pending' ? 'bg-yellow-500/20 text-yellow-400' : 'bg-gray-500/20 text-gray-400'" class="text-xs px-2 py-1 border border-current">
                  {{ statusLabel(order.status) }}
                </span>
              </td>
              <td class="text-right py-3 px-2">
                <button v-if="order.status === 'pending'" class="text-red-400 hover:text-red-300" @click="handleCancel(order.id)">
                  撤单
                </button>
                <span v-else class="text-gray-400">-</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import DataTable from '../components/DataTable.vue'
import ErrorAlert from '../components/ErrorAlert.vue'
import MetricCard from '../components/MetricCard.vue'
import StatusTag from '../components/StatusTag.vue'
import SuccessAlert from '../components/SuccessAlert.vue'
import { usePortfolioStore } from '../stores/portfolio'
import { formatCurrency, formatDateTime } from '../utils/format'
import type { CreateOrderPayload, OrderItem } from '../types/order'

const portfolioStore = usePortfolioStore()

const orderError = ref('')
const portfolioError = ref('')
const successMessage = ref('')

const buyForm = reactive({
  stockCode: '',
  quantity: 0,
  amount: 0
})

const sellForm = reactive({
  stockCode: '',
  quantity: 0,
  amount: 0
})

const selectedStock = ref<{ name: string; price: string } | null>(null)
const selectedSellStock = ref<{ name: string; price: string; quantity: number } | null>(null)

const stockCache: Record<string, { name: string; price: string }> = {
  'sh600519': { name: '贵州茅台', price: '1,789.00' },
  '300750': { name: '宁德时代', price: '235.67' },
  '00700': { name: '腾讯控股', price: '386.40' },
  '09988': { name: '阿里巴巴', price: '87.25' },
  'sh600036': { name: '招商银行', price: '38.92' },
  'sz000001': { name: '平安银行', price: '12.56' }
}

const canBuy = computed(() => {
  return selectedStock.value && buyForm.quantity > 0 && buyForm.amount > 0 && buyForm.amount <= portfolioStore.summary.available_cash
})

const canSell = computed(() => {
  return selectedSellStock.value && sellForm.quantity > 0 && sellForm.quantity <= selectedSellStock.value.quantity
})

const calculateProfitRate = computed(() => {
  if (portfolioStore.summary.market_value === 0) return 0
  return ((portfolioStore.summary.unrealized_pnl / portfolioStore.summary.market_value) * 100).toFixed(2)
})

onMounted(() => {
  void refreshData()
})

async function refreshData(): Promise<void> {
  orderError.value = ''
  portfolioError.value = ''

  try {
    await portfolioStore.loadAllPortfolioData()
  } catch (error: unknown) {
    portfolioError.value = error instanceof Error ? error.message : '交易数据刷新失败'
  }
}

async function submitOrder(): Promise<void> {
  orderError.value = ''
  successMessage.value = ''

  try {
    const payload: CreateOrderPayload = {
      symbol: buyForm.stockCode || sellForm.stockCode,
      side: buyForm.stockCode ? 'buy' : 'sell',
      order_type: 'market',
      quantity: buyForm.quantity || sellForm.quantity,
      price: parseFloat(selectedStock?.value?.price.replace(',', '') || selectedSellStock?.value?.price.replace(',', '') || '0'),
    }

    await portfolioStore.submitOrder(payload)
  } catch (error: unknown) {
    orderError.value = error instanceof Error ? error.message : '下单失败'
  }
}

async function handleCancel(orderId: number): Promise<void> {
  orderError.value = ''
  try {
    await portfolioStore.cancelOrder(orderId)
  } catch (error: unknown) {
    orderError.value = error instanceof Error ? error.message : '撤单失败'
  }
}

async function handleMatchPending(): Promise<void> {
  orderError.value = ''
  try {
    await portfolioStore.matchPendingOrders()
  } catch (error: unknown) {
    orderError.value = error instanceof Error ? error.message : '挂单撮合失败'
  }
}

function searchStock() {
  const code = buyForm.stockCode
  if (stockCache[code]) {
    selectedStock.value = stockCache[code]
    calculateBuyAmount()
  } else {
    selectedStock.value = null
    buyForm.amount = 0
  }
}

function calculateBuyAmount() {
  if (selectedStock.value && buyForm.quantity > 0) {
    const price = parseFloat(selectedStock.value.price.replace(',', ''))
    buyForm.amount = price * buyForm.quantity
  } else {
    buyForm.amount = 0
  }
}

function calculateSellAmount() {
  if (selectedSellStock.value && sellForm.quantity > 0) {
    const price = parseFloat(selectedSellStock.value.price.replace(',', ''))
    sellForm.amount = price * sellForm.quantity
  } else {
    sellForm.amount = 0
  }
}

function setBuyQuantity(quantity: number) {
  buyForm.quantity = quantity
  calculateBuyAmount()
}

function setBuyMax() {
  if (selectedStock.value) {
    const price = parseFloat(selectedStock.value.price.replace(',', ''))
    const maxQuantity = Math.floor(portfolioStore.summary.available_cash / price / 100) * 100
    buyForm.quantity = maxQuantity
    calculateBuyAmount()
  }
}

function onSellStockChange() {
  if (sellForm.stockCode) {
    const position = portfolioStore.positions.find(p => p.symbol === sellForm.stockCode)
    if (position) {
      selectedSellStock.value = {
        name: stockCache[position.symbol]?.name || position.symbol,
        price: position.last_price,
        quantity: position.available_quantity
      }
    }
  } else {
    selectedSellStock.value = null
  }
  sellForm.quantity = 0
  sellForm.amount = 0
}

function setSellPercentage(percentage: number) {
  if (selectedSellStock.value) {
    const quantity = Math.floor(selectedSellStock.value.quantity * percentage / 100) * 100
    sellForm.quantity = quantity
    calculateSellAmount()
  }
}

function setSellAll() {
  if (selectedSellStock.value) {
    sellForm.quantity = selectedSellStock.value.quantity
    calculateSellAmount()
  }
}

function quickSell(position: any) {
  sellForm.stockCode = position.symbol
  onSellStockChange()
}

function viewPositionDetail(position: any) {
  console.log('查看持仓详情:', position)
}

function calculatePositionProfitRate(position: any): string {
  const cost = parseFloat(position.average_cost)
  const current = parseFloat(position.last_price)
  if (cost === 0) return '0.00'
  return (((current - cost) / cost) * 100).toFixed(2)
}

function calculateValueRatio(position: any): string {
  if (portfolioStore.summary.total_equity === 0) return '0.00'
  const value = parseFloat(position.last_price) * position.quantity
  return ((value / portfolioStore.summary.total_equity) * 100).toFixed(2)
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
</script>
