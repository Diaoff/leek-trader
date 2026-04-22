<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex justify-between items-center">
      <h2 class="text-2xl font-bold">盈亏分析</h2>
      <div class="flex space-x-2">
        <button class="px-3 py-1 text-sm bg-dark-secondary hover:bg-dark-card border border-dark-border sharp-btn" @click="setAnalysisPeriod('week')">
          周
        </button>
        <button class="px-3 py-1 text-sm bg-blue-600 text-white sharp-btn" @click="setAnalysisPeriod('month')">
          月
        </button>
        <button class="px-3 py-1 text-sm bg-dark-secondary hover:bg-dark-card border border-dark-border sharp-btn" @click="setAnalysisPeriod('year')">
          年
        </button>
      </div>
    </div>

    <!-- 收益概览卡片 -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-6">
      <div class="card p-5 bg-dark-secondary border border-dark-border">
        <div class="text-sm text-gray-400 font-medium mb-2">总收益</div>
        <div class="text-2xl font-bold text-green-400">+¥{{ formatNumber(analysisData.totalProfit) }}</div>
        <div class="text-sm text-green-400 mt-2">+{{ analysisData.totalProfitPercent }}%</div>
      </div>
      <div class="card p-5 bg-dark-secondary border border-dark-border">
        <div class="text-sm text-gray-400 font-medium mb-2">今日收益</div>
        <div class="text-2xl font-bold text-green-400">+¥{{ formatNumber(analysisData.dailyProfit) }}</div>
        <div class="text-sm text-green-400 mt-2">+{{ analysisData.dailyChangePercent }}%</div>
      </div>
      <div class="card p-5 bg-dark-secondary border border-dark-border">
        <div class="text-sm text-gray-400 font-medium mb-2">本月收益</div>
        <div class="text-2xl font-bold text-green-400">+¥{{ formatNumber(analysisData.monthlyProfit) }}</div>
        <div class="text-sm text-green-400 mt-2">+{{ analysisData.monthlyProfitPercent }}%</div>
      </div>
      <div class="card p-5 bg-dark-secondary border border-dark-border">
        <div class="text-sm text-gray-400 font-medium mb-2">年化收益</div>
        <div class="text-2xl font-bold text-green-400">+{{ analysisData.annualReturn }}%</div>
        <div class="text-sm text-gray-400 mt-2">基于当前持仓</div>
      </div>
    </div>

    <!-- 收益趋势图表 -->
    <div class="card p-5 bg-dark-secondary border border-dark-border">
      <div class="flex justify-between items-center mb-5">
        <h3 class="text-lg font-medium">收益趋势</h3>
        <div class="flex space-x-2">
          <button class="px-3 py-1 text-sm bg-dark-secondary hover:bg-dark-card border border-dark-border sharp-btn" @click="setTrendPeriod('3month')">
            3月
          </button>
          <button class="px-3 py-1 text-sm bg-blue-600 text-white sharp-btn" @click="setTrendPeriod('6month')">
            6月
          </button>
          <button class="px-3 py-1 text-sm bg-dark-secondary hover:bg-dark-card border border-dark-border sharp-btn" @click="setTrendPeriod('1year')">
            1年
          </button>
        </div>
      </div>
      <div class="h-80">
        <canvas ref="trendChart"></canvas>
      </div>
    </div>

    <!-- 持仓盈亏分布 -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div class="card p-5 bg-dark-secondary border border-dark-border">
        <h3 class="text-lg font-medium mb-5">持仓盈亏分布</h3>
        <div class="h-64">
          <canvas ref="distributionChart"></canvas>
        </div>
      </div>
      <div class="card p-5 bg-dark-secondary border border-dark-border">
        <h3 class="text-lg font-medium mb-5">行业分布</h3>
        <div class="h-64">
          <canvas ref="industryChart"></canvas>
        </div>
      </div>
    </div>

    <!-- 交易记录分析 -->
    <div class="card p-5 bg-dark-secondary border border-dark-border">
      <h3 class="text-lg font-medium mb-5">交易记录分析</h3>
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-dark-border">
              <th class="text-left py-3 px-2 text-sm font-medium text-gray-400">股票名称</th>
              <th class="text-right py-3 px-2 text-sm font-medium text-gray-400">交易类型</th>
              <th class="text-right py-3 px-2 text-sm font-medium text-gray-400">价格</th>
              <th class="text-right py-3 px-2 text-sm font-medium text-gray-400">数量</th>
              <th class="text-right py-3 px-2 text-sm font-medium text-gray-400">金额</th>
              <th class="text-right py-3 px-2 text-sm font-medium text-gray-400">日期</th>
              <th class="text-right py-3 px-2 text-sm font-medium text-gray-400">盈亏</th>
            </tr>
          </thead>
          <tbody>
            <tr class="border-b border-dark-border hover:bg-dark-card" v-for="trade in tradeHistory" :key="trade.id">
              <td class="py-3 px-2">
                <div>
                  <div class="font-medium">{{ trade.stockName }}</div>
                  <div class="text-xs text-gray-400">{{ trade.stockCode }}</div>
                </div>
              </td>
              <td class="text-right py-3 px-2">
                <span :class="['px-2 py-1 text-xs rounded', trade.type === 'buy' ? 'bg-blue-500/20 text-blue-400' : 'bg-red-500/20 text-red-400']">
                  {{ trade.type === 'buy' ? '买入' : '卖出' }}
                </span>
              </td>
              <td class="text-right py-3 px-2">{{ trade.price }}</td>
              <td class="text-right py-3 px-2">{{ trade.quantity }}</td>
              <td class="text-right py-3 px-2">{{ trade.amount }}</td>
              <td class="text-right py-3 px-2 text-sm">{{ trade.date }}</td>
              <td class="text-right py-3 px-2" :class="trade.profit >= 0 ? 'text-green-400' : 'text-red-400'">
                {{ trade.profit >= 0 ? '+' : '' }}¥{{ trade.profit }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import Chart from 'chart.js/auto'

const trendChart = ref(null)
const distributionChart = ref(null)
const industryChart = ref(null)
let trendChartInstance = null
let distributionChartInstance = null
let industryChartInstance = null

const analysisData = ref({
  totalProfit: 32500,
  totalProfitPercent: 2.7,
  dailyProfit: 12800,
  dailyChangePercent: 1.1,
  monthlyProfit: 45200,
  monthlyProfitPercent: 3.8,
  annualReturn: 15.6
})

const tradeHistory = ref([
  { id: 1, stockCode: '600519', stockName: '贵州茅台', type: 'buy', price: '1,750.00', quantity: 10, amount: '17,500.00', date: '2024-01-15', profit: 390 },
  { id: 2, stockCode: '300750', stockName: '宁德时代', type: 'sell', price: '245.00', quantity: 100, amount: '24,500.00', date: '2024-01-14', profit: -933 },
  { id: 3, stockCode: '00700', stockName: '腾讯控股', type: 'buy', price: '380.00', quantity: 50, amount: '19,000.00', date: '2024-01-13', profit: 320 },
  { id: 4, stockCode: '09988', stockName: '阿里巴巴', type: 'buy', price: '85.00', quantity: 200, amount: '17,000.00', date: '2024-01-12', profit: 450 }
])

const formatNumber = (num) => {
  return num.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

const initTrendChart = () => {
  if (!trendChart.value) return

  const ctx = trendChart.value.getContext('2d')
  
  if (trendChartInstance) {
    trendChartInstance.destroy()
  }

  trendChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: ['1月', '2月', '3月', '4月', '5月', '6月'],
      datasets: [{
        label: '累计收益',
        data: [5.2, 3.1, 6.6, 14.4, 18.7, 22.5],
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

const initDistributionChart = () => {
  if (!distributionChart.value) return

  const ctx = distributionChart.value.getContext('2d')
  
  if (distributionChartInstance) {
    distributionChartInstance.destroy()
  }

  distributionChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['盈利', '亏损'],
      datasets: [{
        data: [75, 25],
        backgroundColor: [
          '#10b981',
          '#ef4444'
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

const initIndustryChart = () => {
  if (!industryChart.value) return

  const ctx = industryChart.value.getContext('2d')
  
  if (industryChartInstance) {
    industryChartInstance.destroy()
  }

  industryChartInstance = new Chart(ctx, {
    type: 'pie',
    data: {
      labels: ['白酒', '新能源', '互联网', '金融', '医药'],
      datasets: [{
        data: [35, 25, 20, 15, 5],
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

const setAnalysisPeriod = (period) => {
  // 更新分析周期数据
  console.log('设置分析周期:', period)
}

const setTrendPeriod = (period) => {
  // 更新趋势图表数据
  console.log('设置趋势周期:', period)
}

onMounted(async () => {
  await nextTick()
  initTrendChart()
  initDistributionChart()
  initIndustryChart()
})

onUnmounted(() => {
  if (trendChartInstance) {
    trendChartInstance.destroy()
  }
  if (distributionChartInstance) {
    distributionChartInstance.destroy()
  }
  if (industryChartInstance) {
    industryChartInstance.destroy()
  }
})
</script>

<style scoped>
.card {
  border-radius: 4px;
  transition: all 0.2s ease;
}

.card:hover {
  border-color: #3b82f6;
  box-shadow: 0 0 10px rgba(59, 130, 246, 0.1);
}

.sharp-btn {
  border-radius: 0;
}
</style>