<template>
  <section class="space-y-6">
    <ErrorAlert :message="error" type="error" />

    <div class="panel space-y-5">
      <div class="panel-header !mb-0">
        <div>
          <div class="section-label">Stock Pool</div>
          <h3 class="panel-title mt-3">股票池筛选</h3>
          <p class="panel-subtitle">
            先用证券目录完成市场、关键词、ST 与标签筛选，结果可直接加入自选盯盘。
          </p>
        </div>
        <button class="secondary-button" type="button" :disabled="loading" @click="loadPool">
          {{ loading ? '筛选中...' : '重新筛选' }}
        </button>
      </div>

      <div class="grid gap-4 lg:grid-cols-[180px_minmax(220px,1fr)_160px_160px_160px_160px]">
        <div>
          <label class="field-label" for="pool-market">市场</label>
          <select id="pool-market" v-model="filters.market" class="field-select">
            <option value="all">全部 A 股</option>
            <option value="sh">沪A</option>
            <option value="sz">深A</option>
            <option value="bj">北交所</option>
          </select>
        </div>
        <div>
          <label class="field-label" for="pool-query">关键词</label>
          <input
            id="pool-query"
            v-model.trim="filters.query"
            class="field-input"
            type="text"
            placeholder="代码 / 名称 / 拼音缩写"
            @keyup.enter="loadPool"
          />
        </div>
        <div>
          <label class="field-label" for="pool-tag">标签</label>
          <select id="pool-tag" v-model="filters.tag" class="field-select">
            <option value="">不限</option>
            <option value="创">创业板</option>
            <option value="ST">ST</option>
          </select>
        </div>
        <div>
          <label class="field-label" for="pool-min-cap">最小市值</label>
          <input id="pool-min-cap" v-model.number="filters.minMarketCapYi" class="field-input" type="number" min="0" placeholder="亿元" />
        </div>
        <div>
          <label class="field-label" for="pool-max-cap">最大市值</label>
          <input id="pool-max-cap" v-model.number="filters.maxMarketCapYi" class="field-input" type="number" min="0" placeholder="亿元" />
        </div>
        <div>
          <label class="field-label" for="pool-limit">数量</label>
          <select id="pool-limit" v-model.number="filters.limit" class="field-select">
            <option :value="20">20</option>
            <option :value="50">50</option>
            <option :value="100">100</option>
            <option :value="200">200</option>
          </select>
        </div>
      </div>

      <label class="inline-flex items-center gap-3 text-sm text-[var(--text-secondary)]">
        <input v-model="filters.excludeSt" type="checkbox" />
        排除 ST 标的
      </label>
    </div>

    <div class="panel">
      <div class="panel-header">
        <div>
          <h3 class="panel-title">筛选结果</h3>
          <p class="panel-subtitle">共 {{ results.length }} 个候选，优先展示本地证券目录中的基础字段。</p>
        </div>
        <RouterLink class="ghost-button" to="/watchlist">进入自选股</RouterLink>
      </div>

      <div v-if="loading" class="empty-state">
        <div>正在筛选股票池...</div>
      </div>
      <div v-else-if="results.length === 0" class="empty-state">
        <div>暂无匹配标的</div>
        <div class="text-sm text-[var(--text-tertiary)]">放宽市场、关键词或标签条件后重试。</div>
      </div>
      <div v-else class="table-shell">
        <table class="data-table">
          <thead>
            <tr>
              <th>标的</th>
              <th>市场</th>
              <th>市值</th>
              <th>标签</th>
              <th>拼音</th>
              <th>自选状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in results" :key="item.symbol">
              <td>
                <RouterLink class="font-semibold transition hover:text-[var(--accent)]" :to="{ name: 'stock-detail', params: { symbol: item.symbol } }">
                  {{ item.name }}
                </RouterLink>
                <div class="mono-data muted-text mt-1">{{ item.code }}</div>
              </td>
              <td>{{ item.market }}</td>
              <td class="mono-data">{{ formatMarketCap(item.market_cap) }}</td>
              <td>
                <div class="flex flex-wrap gap-2">
                  <span v-for="tag in item.tags" :key="tag" class="status-chip neutral">{{ tag }}</span>
                  <span v-if="item.tags.length === 0" class="muted-text">--</span>
                </div>
              </td>
              <td class="mono-data">{{ item.pinyin_abbr || '--' }}</td>
              <td>
                <span :class="['status-chip', item.in_watchlist ? 'positive' : 'neutral']">
                  {{ item.in_watchlist ? '已在自选' : '未加入' }}
                </span>
              </td>
              <td>
                <button
                  class="secondary-button"
                  type="button"
                  :disabled="item.in_watchlist || addingSymbol === item.symbol"
                  @click="addToWatchlist(item)"
                >
                  {{ item.in_watchlist ? '已加入' : '加入自选' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { ElMessage } from 'element-plus'

import ErrorAlert from '../components/ErrorAlert.vue'
import { screenSecurities, type SecurityScreenResult } from '../api/securities'
import { createWatchlist } from '../api/watchlists'
import { getApiErrorMessage } from '../utils/http'

const filters = reactive({
  market: 'all',
  query: '',
  tag: '',
  excludeSt: true,
  minMarketCapYi: null as number | null,
  maxMarketCapYi: null as number | null,
  limit: 50,
})
const results = ref<SecurityScreenResult[]>([])
const loading = ref(false)
const error = ref('')
const addingSymbol = ref('')
let reloadTimer: number | undefined

async function loadPool() {
  loading.value = true
  error.value = ''
  try {
    results.value = await screenSecurities({
      market: filters.market,
      q: filters.query || null,
      exclude_st: filters.excludeSt,
      tags: filters.tag ? [filters.tag] : [],
      min_market_cap: toMarketCap(filters.minMarketCapYi),
      max_market_cap: toMarketCap(filters.maxMarketCapYi),
      limit: filters.limit,
    })
  } catch (err: unknown) {
    error.value = getApiErrorMessage(err, '股票池筛选失败')
  } finally {
    loading.value = false
  }
}

async function addToWatchlist(item: SecurityScreenResult) {
  addingSymbol.value = item.symbol
  error.value = ''
  try {
    await createWatchlist({ symbol: item.symbol })
    item.in_watchlist = true
    ElMessage.success(`${item.name} 已加入自选股`)
  } catch (err: unknown) {
    error.value = getApiErrorMessage(err, '加入自选股失败')
  } finally {
    addingSymbol.value = ''
  }
}

watch(
  () => [filters.market, filters.tag, filters.excludeSt, filters.minMarketCapYi, filters.maxMarketCapYi, filters.limit],
  () => loadPool(),
)

watch(
  () => filters.query,
  () => {
    window.clearTimeout(reloadTimer)
    reloadTimer = window.setTimeout(() => loadPool(), 300)
  },
)

onMounted(() => loadPool())

function toMarketCap(value: number | null): number | null {
  return value && value > 0 ? value * 100000000 : null
}

function formatMarketCap(value: number | null): string {
  if (value === null || value === undefined) {
    return '--'
  }
  return `${(value / 100000000).toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 亿`
}
</script>
