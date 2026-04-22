<template>
  <section class="flex flex-col gap-6">
    <div class="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <h2 class="page-title">策略中心</h2>
        <p class="page-subtitle">当前版本只展示内置策略的最近一次信号结果，不做编辑、调度和回测。</p>
      </div>
      <el-button text :loading="loading" @click="loadStrategies">刷新</el-button>
    </div>

    <el-alert
      v-if="errorMessage"
      :closable="false"
      :title="errorMessage"
      type="warning"
      show-icon
    />

    <el-card class="surface-card">
      <el-table v-loading="loading" :data="strategies" stripe empty-text="暂无策略数据">
        <el-table-column prop="name" label="策略名称" min-width="180" />
        <el-table-column label="类型" min-width="120">
          <template #default="{ row }">{{ strategyTypeLabel(row.strategy_type) }}</template>
        </el-table-column>
        <el-table-column label="状态" min-width="110">
          <template #default="{ row }">
            <el-tag class="pill-tag" :type="row.status === 'active' ? 'success' : 'info'">
              {{ row.status === 'active' ? '启用中' : row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最新信号" min-width="120">
          <template #default="{ row }">
            <el-tag class="pill-tag" :type="signalTagType(row.latest_signal)">
              {{ signalLabel(row.latest_signal) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="signal_symbol" label="标的" min-width="120" />
        <el-table-column label="参数" min-width="260">
          <template #default="{ row }">
            <div class="flex flex-wrap gap-2">
              <el-tag
                v-for="entry in formatParameters(row.parameters)"
                :key="entry"
                class="pill-tag"
                effect="plain"
                type="info"
              >
                {{ entry }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchStrategies, type StrategyItem } from '../api/strategies'
import { getApiErrorMessage } from '../utils/http'

const loading = ref(false)
const errorMessage = ref('')
const strategies = ref<StrategyItem[]>([])

onMounted(() => {
  void loadStrategies()
})

async function loadStrategies(): Promise<void> {
  loading.value = true
  errorMessage.value = ''

  try {
    strategies.value = await fetchStrategies()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error, '策略数据加载失败')
    strategies.value = []
  } finally {
    loading.value = false
  }
}

function strategyTypeLabel(strategyType: string): string {
  const mapping: Record<string, string> = {
    moving_average: '双均线',
    macd: 'MACD',
  }
  return mapping[strategyType] ?? strategyType
}

function signalLabel(signal: string): string {
  const mapping: Record<string, string> = {
    buy: '买入',
    sell: '卖出',
    hold: '观望',
  }
  return mapping[signal] ?? signal
}

function signalTagType(signal: string): 'success' | 'danger' | 'info' {
  if (signal === 'buy') {
    return 'success'
  }
  if (signal === 'sell') {
    return 'danger'
  }
  return 'info'
}

function formatParameters(parameters: StrategyItem['parameters']): string[] {
  return Object.entries(parameters).map(([key, value]) => `${key}: ${value}`)
}
</script>
