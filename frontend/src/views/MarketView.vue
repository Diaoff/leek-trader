<template>
  <section class="flex flex-col gap-6">
    <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <h2 class="page-title">行情中心</h2>
        <p class="page-subtitle">优先按我的自选拉取实时快照，也支持临时手动输入股票代码批量查询。</p>
      </div>

      <div class="flex w-full flex-col gap-3 md:flex-row lg:w-auto">
        <el-input
          v-model="symbolInput"
          clearable
          placeholder="例如 sh600519,sz000001"
          @keyup.enter="loadManualQuotes"
        />
        <div class="flex gap-2">
          <el-button type="primary" :loading="quotesLoading" @click="loadManualQuotes">手动查询</el-button>
          <el-button v-if="watchlists.length > 0" :loading="quotesLoading" @click="loadWatchlistQuotes">
            查看自选
          </el-button>
        </div>
      </div>
    </div>

    <el-alert
      v-if="watchlistErrorMessage"
      :closable="false"
      :title="watchlistErrorMessage"
      type="warning"
      show-icon
    />
    <el-alert
      v-if="quoteErrorMessage"
      :closable="false"
      :title="quoteErrorMessage"
      type="warning"
      show-icon
    />

    <div class="grid grid-cols-1 gap-4 xl:grid-cols-[360px_1fr]">
      <el-card class="surface-card">
        <template #header>
          <div class="flex items-center justify-between gap-4">
            <span class="font-semibold">我的自选</span>
            <span class="muted-text text-sm">{{ watchlists.length }} 只</span>
          </div>
        </template>

        <div class="flex flex-col gap-4">
          <div class="flex gap-2">
            <el-input
              v-model="watchlistInput"
              clearable
              placeholder="输入代码，例如 sh600519"
              @keyup.enter="handleCreateWatchlist"
            />
            <el-button type="primary" :loading="watchlistSubmitting" @click="handleCreateWatchlist">
              添加
            </el-button>
          </div>

          <div v-loading="watchlistLoading" class="flex min-h-48 flex-col gap-2">
            <template v-if="watchlists.length > 0">
              <div
                v-for="item in watchlists"
                :key="item.id"
                class="flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/5 px-4 py-3"
              >
                <button
                  class="text-left text-sm font-semibold text-slate-100 transition hover:text-emerald-300"
                  type="button"
                  @click="handleSelectWatchlist(item.symbol)"
                >
                  {{ item.symbol }}
                </button>
                <el-button text type="danger" @click="handleDeleteWatchlist(item.id)">删除</el-button>
              </div>
            </template>
            <div v-else class="flex flex-1 items-center justify-center rounded-2xl border border-dashed border-white/10 px-4 text-sm text-slate-400">
              还没有自选股，添加后会默认作为行情页的查询列表。
            </div>
          </div>
        </div>
      </el-card>

      <el-card class="surface-card">
        <template #header>
          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <span class="font-semibold">行情快照</span>
              <span class="muted-text text-sm">当前来源：{{ activeSourceLabel }}</span>
            </div>
            <span class="muted-text text-sm">共 {{ quotes.length }} 条</span>
          </div>
        </template>

        <el-table v-loading="quotesLoading" :data="quotes" stripe empty-text="暂无行情数据">
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
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { fetchQuotes, type QuoteItem } from '../api/quotes'
import {
  createWatchlist,
  deleteWatchlist,
  fetchWatchlists,
  type WatchlistItem,
} from '../api/watchlists'
import { formatCurrency, formatDateTime, formatDecimal } from '../utils/format'
import { getApiErrorMessage } from '../utils/http'

const DEFAULT_SYMBOLS = ['sh600519', 'sz000001', 'sh600036', 'sz300750']

type QuoteSource = 'watchlist' | 'manual' | 'default'

const quotesLoading = ref(false)
const watchlistLoading = ref(false)
const watchlistSubmitting = ref(false)
const quoteErrorMessage = ref('')
const watchlistErrorMessage = ref('')
const quotes = ref<QuoteItem[]>([])
const watchlists = ref<WatchlistItem[]>([])
const symbolInput = ref(DEFAULT_SYMBOLS.join(','))
const watchlistInput = ref('')
const activeSource = ref<QuoteSource>('default')

const activeSourceLabel = computed(() => {
  if (activeSource.value === 'watchlist') {
    return '我的自选'
  }
  if (activeSource.value === 'manual') {
    return '手动查询'
  }
  return '默认示例'
})

onMounted(() => {
  void initializeView()
})

async function initializeView(): Promise<void> {
  await loadWatchlists()
  await loadInitialQuotes()
}

async function loadWatchlists(): Promise<void> {
  watchlistLoading.value = true
  watchlistErrorMessage.value = ''

  try {
    watchlists.value = await fetchWatchlists()
  } catch (error) {
    watchlistErrorMessage.value = getApiErrorMessage(error, '自选列表加载失败')
    watchlists.value = []
  } finally {
    watchlistLoading.value = false
  }
}

async function loadInitialQuotes(): Promise<void> {
  if (watchlists.value.length > 0) {
    await loadWatchlistQuotes()
    return
  }
  await loadQuotesBySymbols(DEFAULT_SYMBOLS, 'default')
}

async function loadManualQuotes(): Promise<void> {
  const symbols = parseSymbols(symbolInput.value)
  await loadQuotesBySymbols(symbols.length > 0 ? symbols : DEFAULT_SYMBOLS, symbols.length > 0 ? 'manual' : 'default')
}

async function loadWatchlistQuotes(): Promise<void> {
  const symbols = watchlists.value.map((item) => item.symbol)
  await loadQuotesBySymbols(symbols.length > 0 ? symbols : DEFAULT_SYMBOLS, symbols.length > 0 ? 'watchlist' : 'default')
}

async function loadQuotesBySymbols(symbols: string[], source: QuoteSource): Promise<void> {
  quotesLoading.value = true
  quoteErrorMessage.value = ''

  try {
    quotes.value = await fetchQuotes(symbols)
    activeSource.value = source
  } catch (error) {
    quoteErrorMessage.value = getApiErrorMessage(error, '行情加载失败，请稍后重试。')
    quotes.value = []
  } finally {
    quotesLoading.value = false
  }
}

async function handleCreateWatchlist(): Promise<void> {
  watchlistSubmitting.value = true
  watchlistErrorMessage.value = ''

  try {
    const item = await createWatchlist({ symbol: watchlistInput.value })
    watchlistInput.value = ''
    await loadWatchlists()
    await loadWatchlistQuotes()
    ElMessage.success(`${item.symbol} 已加入自选`)
  } catch (error) {
    const message = getApiErrorMessage(error, '添加自选失败')
    watchlistErrorMessage.value = message
    ElMessage.error(message)
  } finally {
    watchlistSubmitting.value = false
  }
}

async function handleDeleteWatchlist(itemId: number): Promise<void> {
  watchlistErrorMessage.value = ''

  try {
    await deleteWatchlist(itemId)
    await loadWatchlists()
    await loadWatchlistQuotes()
    ElMessage.success('已从自选移除')
  } catch (error) {
    const message = getApiErrorMessage(error, '删除自选失败')
    watchlistErrorMessage.value = message
    ElMessage.error(message)
  }
}

async function handleSelectWatchlist(symbol: string): Promise<void> {
  symbolInput.value = symbol
  await loadQuotesBySymbols([symbol], 'manual')
}

function parseSymbols(input: string): string[] {
  return input
    .split(',')
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean)
}
</script>
