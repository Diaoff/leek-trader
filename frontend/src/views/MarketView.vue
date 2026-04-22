<template>
  <section class="flex flex-col gap-6">
    <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <h2 class="page-title">行情中心</h2>
        <p class="page-subtitle">使用后端行情 fallback 链路展示实时快照，支持手动输入股票代码批量查询。</p>
      </div>

      <div class="flex w-full gap-3 lg:w-auto">
        <el-input
          v-model="symbolInput"
          clearable
          placeholder="例如 sh600519,sz000001"
          @keyup.enter="loadQuotes"
        />
        <el-button type="primary" :loading="loading" @click="loadQuotes">刷新</el-button>
      </div>
    </div>

    <el-alert
      v-if="errorMessage"
      :closable="false"
      :title="errorMessage"
      type="warning"
      show-icon
    />

    <el-card class="surface-card">
      <template #header>
        <div class="flex items-center justify-between gap-4">
          <span class="font-semibold">行情快照</span>
          <span class="muted-text text-sm">共 {{ quotes.length }} 条</span>
        </div>
      </template>

      <el-table v-loading="loading" :data="quotes" stripe empty-text="暂无行情数据">
        <el-table-column prop="symbol" label="代码" min-width="140" />
        <el-table-column label="状态" min-width="100">
          <template #default="{ row }">
            <el-tag class="pill-tag" :type="row.is_halted ? 'warning' : 'success'">
              {{ row.is_halted ? '停牌/异常' : '正常' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="现价" min-width="120">
          <template #default="{ row }">{{ formatCurrency(row.price) }}</template>
        </el-table-column>
        <el-table-column label="涨跌幅" min-width="120">
          <template #default="{ row }">
            <span :class="row.change_percent >= 0 ? 'text-emerald-600' : 'text-rose-600'">
              {{ row.change_percent.toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column label="成交量" min-width="140">
          <template #default="{ row }">{{ formatDecimal(row.volume, 0) }}</template>
        </el-table-column>
        <el-table-column label="时间" min-width="180">
          <template #default="{ row }">{{ formatDateTime(row.timestamp) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchQuotes, type QuoteItem } from '../api/quotes'
import { formatCurrency, formatDateTime, formatDecimal } from '../utils/format'
import { getApiErrorMessage } from '../utils/http'

const DEFAULT_SYMBOLS = ['sh600519', 'sz000001', 'sh600036', 'sz300750']

const loading = ref(false)
const errorMessage = ref('')
const quotes = ref<QuoteItem[]>([])
const symbolInput = ref(DEFAULT_SYMBOLS.join(','))

onMounted(() => {
  void loadQuotes()
})

async function loadQuotes(): Promise<void> {
  loading.value = true
  errorMessage.value = ''

  try {
    const symbols = symbolInput.value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)

    quotes.value = await fetchQuotes(symbols.length > 0 ? symbols : DEFAULT_SYMBOLS)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error, '行情加载失败，请稍后重试。')
    quotes.value = []
  } finally {
    loading.value = false
  }
}
</script>
