<template>
  <div class="space-y-6">
    <!-- Summary Cards -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
      <div class="card p-5 relative sharp-card animate-fadeIn" style="animation-delay: 0.1s;">
        <div class="flex justify-between items-start mb-4">
          <div>
            <h3 class="text-sm text-gray-400 font-medium">总资产</h3>
            <p class="text-3xl font-bold mt-1">¥{{ formatNumber(portfolioData.totalAsset) }}</p>
          </div>
          <div class="p-2 rounded-full bg-blue-500/10 text-blue-400">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
        </div>
        <div class="flex items-center">
          <span class="text-green-400 text-sm font-medium flex items-center">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
            +{{ portfolioData.dailyChangePercent }}% 今日
          </span>
          <div class="h-px flex-grow ml-3 bg-gradient-to-r from-green-500 to-transparent"></div>
        </div>
      </div>
      <div class="card p-5 relative sharp-card animate-fadeIn" style="animation-delay: 0.2s;">
        <div class="flex justify-between items-start mb-4">
          <div>
            <h3 class="text-sm text-gray-400 font-medium">总盈亏</h3>
            <p class="text-3xl font-bold mt-1 text-green-400">+¥{{ formatNumber(portfolioData.totalProfit) }}</p>
          </div>
          <div class="p-2 rounded-full bg-green-500/10 text-green-400">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
          </div>
        </div>
        <div class="flex items-center">
          <span class="text-green-400 text-sm font-medium flex items-center">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
            +{{ portfolioData.totalProfitPercent }}% 持仓
          </span>
          <div class="h-px flex-grow ml-3 bg-gradient-to-r from-green-500 to-transparent"></div>
        </div>
      </div>
      <div class="card p-5 relative sharp-card animate-fadeIn" style="animation-delay: 0.3s;">
        <div class="flex justify-between items-start mb-4">
          <div>
            <h3 class="text-sm text-gray-400 font-medium">今日盈亏</h3>
            <p class="text-3xl font-bold mt-1 text-green-400">+¥{{ formatNumber(portfolioData.dailyProfit) }}</p>
          </div>
          <div class="p-2 rounded-full bg-yellow-500/10 text-yellow-400">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
        </div>
        <div class="flex items-center">
          <span class="text-green-400 text-sm font-medium flex items-center">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
            +{{ portfolioData.dailyChangePercent }}% 今日
          </span>
          <div class="h-px flex-grow ml-3 bg-gradient-to-r from-green-500 to-transparent"></div>
        </div>
      </div>
    </div>

    <!-- Charts -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div class="card p-5 animate-fadeIn" style="animation-delay: 0.4s;">
        <div class="flex justify-between items-center mb-5">
          <h3 class="text-lg font-medium">持仓概览</h3>
          <div class="flex space-x-2">
            <button class="px-3 py-1 text-sm bg-dark-secondary hover:bg-dark-card border border-dark-border sharp-btn" @click="setPortfolioPeriod('week')">
              周
            </button>
            <button class="px-3 py-1 text-sm bg-blue-600 text-white sharp-btn" @click="setPortfolioPeriod('month')">
              月
            </button>
            <button class="px-3 py-1 text-sm bg-dark-secondary hover:bg-dark-card border border-dark-border sharp-btn" @click="setPortfolioPeriod('year')">
              年
            </button>
          </div>
        </div>
        <div class="h-64">
          <canvas ref="portfolioChart"></canvas>
        </div>
      </div>
      <div class="card p-5 animate-fadeIn" style="animation-delay: 0.5s;">
        <div class="flex justify-between items-center mb-5">
          <h3 class="text-lg font-medium">收益趋势</h3>
          <div class="flex space-x-2">
            <button class="px-3 py-1 text-sm bg-dark-secondary hover:bg-dark-card border border-dark-border sharp-btn" @click="setProfitPeriod('3month')">
              3月
            </button>
            <button class="px-3 py-1 text-sm bg-blue-600 text-white sharp-btn" @click="setProfitPeriod('6month')">
              6月
            </button>
            <button class="px-3 py-1 text-sm bg-dark-secondary hover:bg-dark-card border border-dark-border sharp-btn" @click="setProfitPeriod('1year')">
              1年
            </button>
          </div>
        </div>
        <div class="h-64">
          <canvas ref="profitChart"></canvas>
        </div>
      </div>
    </div>

    <!-- Watchlist Preview -->
    <div class="card p-5 animate-fadeIn" style="animation-delay: 0.6s;">
      <div class="flex justify-between items-center mb-5">
        <h3 class="text-lg font-medium">自选股实时行情</h3>
        <button class="text-blue-400 hover:text-blue-300 text-sm flex items-center" @click="navigateToMarket">
          查看全部
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 ml-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-dark-border">
              <th class="text-left py-3 px-2 text-sm font-medium text-gray-400">股票名称</th>
              <th class="text-right py-3 px-2 text-sm font-medium text-gray-400">最新价</th>
              <th class="text-right py-3 px-2 text-sm font-medium text-gray-400">涨跌幅</th>
              <th class="text-right py-3 px-2 text-sm font-medium text-gray-400">成交量</th>
              <th class="text-right py-3 px-2 text-sm font-medium text-gray-400">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr class="border-b border-dark-border hover:bg-dark-secondary/50" v-for="stock in watchlist" :key="stock.code">
              <td class="py-3 px-2">
                <div>
                  <div class="font-medium">{{ stock.name }}</div>
                  <div class="text-xs text-gray-400">{{ stock.code }}</div>
                </div>
              </td>
              <td class="text-right py-3 px-2 font-medium">{{ stock.price }}</td>
              <td class="text-right py-3 px-2" :class="stock.change >= 0 ? 'text-green-400' : 'text-red-400'">
                {{ stock.change >= 0 ? '+' : '' }}{{ stock.change }}%
              </td>
              <td class="text-right py-3 px-2">{{ stock.volume }}</td>
              <td class="text-right py-3 px-2">
                <button class="text-blue-400 hover:text-blue-300 mr-2" @click="viewStockDetail(stock)">
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                  </svg>
                </button>
                <button class="text-green-400 hover:text-green-300" @click="buyStock(stock)">
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                  </svg>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Active Strategies -->
    <div class="card p-5 animate-fadeIn" style="animation-delay: 0.7s;">
      <div class="flex justify-between items-center mb-5">
        <h3 class="text-lg font-medium">活跃策略</h3>
        <button class="text-blue-400 hover:text-blue-300 text-sm flex items-center" @click="navigateToStrategies">
          管理策略
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 ml-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div class="bg-dark-secondary border border-dark-border p-4 hover:border-blue-500/50 transition-colors" v-for="strategy in activeStrategies" :key="strategy.id">
          <div class="flex justify-between items-start mb-3">
            <h4 class="font-medium">{{ strategy.name }}</h4>
            <span class="bg-green-500/20 text-green-400 text-xs px-2 py-1 border border-green-500/30">运行中</span>
          </div>
          <div class="space-y-2 text-sm">
            <div class="flex justify-between">
              <span class="text-gray-400">信号数</span>
              <span>{{ strategy.signals }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-gray-400">今日收益</span>
              <span class="text-green-400">+¥{{ formatNumber(strategy.dailyProfit) }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-gray-400">总收益</span>
              <span class="text-green-400">+{{ strategy.totalReturn }}%</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import Chart from 'chart.js/auto'

const router = useRouter()
const portfolioChart = ref(null)
const profitChart = ref(null)
let portfolioChartInstance = null
let profitChartInstance = null

const portfolioData = ref({
  totalAsset: 1250000,
  totalProfit: 32500,
  totalProfitPercent: 2.7,
  dailyProfit: 12800,
  dailyChangePercent: 1.1
})

const watchlist = ref([
  { code: '600519', name: '贵州茅台', price: '1,789.00', change: 2.34, volume: '89.2万' },
  { code: '300750', name: '宁德时代', price: '235.67', change: -1.25, volume: '124.5万' },
  { code: '00700', name: '腾讯控股', price: '386.40', change: 0.87, volume: '56.3万' },
  { code: '09988', name: '阿里巴巴', price: '87.25', change: 1.55, volume: '92.1万' }
])

const activeStrategies = ref([
  { id: 1, name: '双均线策略', signals: 12, dailyProfit: 3500, totalReturn: 15.8 },
  { id: 2, name: 'MACD金叉策略', signals: 8, dailyProfit: 2800, totalReturn: 12.3 },
  { id: 3, name: '网格交易策略', signals: 24, dailyProfit: 4200, totalReturn: 8.5 }
])

const formatNumber = (num) => {
  return num.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

const initPortfolioChart = () => {
  if (!portfolioChart.value) return

  const ctx = portfolioChart.value.getContext('2d')
  
  if (portfolioChartInstance) {
    portfolioChartInstance.destroy()
  }

  portfolioChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['贵州茅台', '宁德时代', '腾讯控股', '阿里巴巴', '其他'],
      datasets: [{
        data: [14.31, 12.56, 10.23, 8.75, 54.15],
        backgroundColor: [
          '#3b82f6',
          '#10b981',
          '#f59e0b',
          '#ef4444',
          '#8b5cf6'
        ],
        borderColor: '#1e293b',
        borderWidth: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            color: '#94a3b8',
            padding: 20,
            usePointStyle: true,
            pointStyle: 'circle'
          }
        }
      }
    }
  })
}

const initProfitChart = () => {
  if (!profitChart.value) return

  const ctx = profitChart.value.getContext('2d')
  
  if (profitChartInstance) {
    profitChartInstance.destroy()
  }

  profitChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: ['1月', '2月', '3月', '4月', '5月', '6月'],
      datasets: [{
        label: '月度收益',
        data: [5.2, -2.1, 3.5, 7.8, 4.3, 2.5],
        borderColor: '#10b981',
        backgroundColor: 'rgba(16, 185, 129, 0.1)',
        fill: true,
        tension: 0.4,
        pointBackgroundColor: '#ffffff',
        pointBorderColor: '#10b981',
        pointBorderWidth: 2,
        pointRadius: 4,
        pointHoverRadius: 6
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          mode: 'index',
          intersect: false,
          backgroundColor: 'rgba(15, 23, 42, 0.9)',
          titleColor: '#e2e8f0',
          bodyColor: '#94a3b8',
          borderColor: '#2a3a50',
          borderWidth: 1,
          padding: 10,
          displayColors: false,
          callbacks: {
            label: function(context) {
              return `收益: ${context.parsed.y}%`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: {
            color: 'rgba(71, 85, 105, 0.2)',
            borderColor: 'rgba(71, 85, 105, 0.3)'
          },
          ticks: {
            color: '#94a3b8'
          }
        },
        y: {
          grid: {
            color: 'rgba(71, 85, 105, 0.2)',
            borderColor: 'rgba(71, 85, 105, 0.3)'
          },
          ticks: {
            color: '#94a3b8',
            callback: function(value) {
              return value + '%';
            }
          }
        }
      }
    }
  })
}

const setPortfolioPeriod = (period) => {
  // 更新持仓图表数据
  console.log('设置持仓周期:', period)
}

const setProfitPeriod = (period) => {
  // 更新收益图表数据
  console.log('设置收益周期:', period)
}

const viewStockDetail = (stock) => {
  console.log('查看股票详情:', stock)
}

const buyStock = (stock) => {
  console.log('买入股票:', stock)
  router.push('/portfolio')
}

const navigateToMarket = () => {
  router.push('/market')
}

const navigateToStrategies = () => {
  router.push('/strategies')
}

const simulateDataUpdates = () => {
  // 模拟数据更新
  watchlist.value.forEach(stock => {
    const change = (Math.random() * 0.6 - 0.3).toFixed(2)
    stock.change = parseFloat(change)
    const price = parseFloat(stock.price.replace(',', ''))
    const newPrice = (price * (1 + stock.change / 100)).toFixed(2)
    stock.price = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(newPrice)
  })
}

let updateInterval = null

onMounted(async () => {
  await nextTick()
  initPortfolioChart()
  initProfitChart()
  
  // 启动数据更新
  updateInterval = setInterval(simulateDataUpdates, 5000)
})

onUnmounted(() => {
  if (updateInterval) {
    clearInterval(updateInterval)
  }
  if (portfolioChartInstance) {
    portfolioChartInstance.destroy()
  }
  if (profitChartInstance) {
    profitChartInstance.destroy()
  }
})
</script>

<style scoped>
.card {
  background-color: #1e293b;
  border: 1px solid #334155;
  border-radius: 4px;
  transition: all 0.2s ease;
}

.card:hover {
  border-color: #3b82f6;
  box-shadow: 0 0 10px rgba(59, 130, 246, 0.1);
}

.bg-dark-secondary {
  background-color: #1e293b;
}

.bg-dark-card {
  background-color: #2a3a50;
}

.border-dark-border {
  border-color: #334155;
}

.sharp-btn {
  border-radius: 0;
}

.sharp-card {
  border-radius: 0;
}

.animate-fadeIn {
  animation: fadeIn 0.5s ease-in-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
