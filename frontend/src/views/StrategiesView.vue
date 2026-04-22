<template>
  <section class="flex flex-col gap-6">
    <div class="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
      <PageHeader
        title="策略中心"
        subtitle="当前版本只展示内置策略的最近一次信号结果，不做编辑、调度和回测。"
      />
      <el-button text :loading="store.loading" @click="loadStrategies">
        刷新
      </el-button>
    </div>

    <ErrorAlert :message="store.error" />

    <el-card class="surface-card">
      <DataTable :data="store.strategies" :loading="store.loading" empty-text="暂无策略数据">
        <el-table-column prop="name" label="策略名称" min-width="180" />
        <el-table-column label="类型" min-width="120">
          <template #default="{ row }">
            {{ strategyTypeLabel(row.strategy_type) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" min-width="110">
          <template #default="{ row }">
            <StatusTag
              :label="row.status === 'active' ? '启用中' : row.status"
              :type="row.status === 'active' ? 'success' : 'info'"
            />
          </template>
        </el-table-column>
        <el-table-column label="最新信号" min-width="120">
          <template #default="{ row }">
            <StatusTag
              :label="signalLabel(row.latest_signal)"
              :type="signalTagType(row.latest_signal)"
            />
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
      </DataTable>
    </el-card>
  </section>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'

import DataTable from '../components/DataTable.vue'
import ErrorAlert from '../components/ErrorAlert.vue'
import PageHeader from '../components/PageHeader.vue'
import StatusTag from '../components/StatusTag.vue'
import { useStrategyStore } from '../stores/strategies'
import type { StrategyItem } from '../types/strategy'

const store = useStrategyStore()

onMounted(() => {
  void loadStrategies()
})

async function loadStrategies(): Promise<void> {
  await store.fetchStrategies()
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
