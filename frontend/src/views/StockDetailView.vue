<template>
  <section class="stock-detail-page space-y-4">
    <div class="panel stock-detail-hero">
      <div>
        <div class="header-kicker">Stock Detail</div>
        <h1 class="page-title">个股详情</h1>
        <p class="page-subtitle">内嵌东方财富个股走势页，集中查看盘口、分时/K线、买卖盘和筹码信息。</p>
      </div>

      <div class="stock-detail-actions">
        <div class="stock-search-inline">
          <label class="field-label" for="stock-detail-symbol">股票代码</label>
          <div class="stock-search-row">
            <input
              id="stock-detail-symbol"
              v-model.trim="symbolDraft"
              class="field-input"
              type="text"
              placeholder="例如 600519 / sh600519 / 301667.SZ"
              @keyup.enter="openDraftSymbol"
            />
            <button class="primary-button" type="button" :disabled="!symbolDraft" @click="openDraftSymbol">
              查看
            </button>
          </div>
        </div>
        <button class="secondary-button" type="button" @click="goBack">返回</button>
      </div>
    </div>

    <div class="panel stock-detail-meta-panel">
      <div class="stock-detail-meta">
        <div>
          <div class="stock-detail-symbol mono-data">{{ target.symbol || '--' }}</div>
          <div class="panel-subtitle">secid {{ target.secid || '--' }} · market {{ target.market || '--' }}</div>
        </div>
        <div class="token-row">
          <span :class="['status-chip', target.isIndex ? 'subtle' : 'positive']">
            {{ target.isIndex ? '指数页面' : '个股增强页面' }}
          </span>
          <a class="secondary-button" :href="target.fallbackUrl" target="_blank" rel="noreferrer">
            浏览器打开
          </a>
        </div>
      </div>
    </div>

    <div v-if="!target.symbol" class="panel empty-state">
      <div>请输入股票代码查看详情</div>
      <div class="text-sm text-[var(--text-tertiary)]">支持 A 股常见格式：600519、sh600519、301667.SZ。</div>
    </div>

    <div v-else class="panel stock-detail-frame-panel">
      <div class="stock-detail-frame-toolbar">
        <span class="status-chip subtle">数据源：东方财富</span>
        <span class="mono-data muted-text">{{ target.url }}</span>
      </div>
      <iframe
        :key="target.url"
        class="stock-detail-frame"
        :src="target.url"
        title="个股详情走势"
        loading="lazy"
        referrerpolicy="no-referrer-when-downgrade"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

interface StockDetailTarget {
  symbol: string
  code: string
  market: string
  secid: string
  url: string
  fallbackUrl: string
  isIndex: boolean
}

const eastMoneyHost = 'https://quote.eastmoney.com'

const route = useRoute()
const router = useRouter()

const routeSymbol = computed(() => String(route.params.symbol ?? route.query.symbol ?? ''))
const symbolDraft = ref(routeSymbol.value)
const target = computed(() => buildStockDetailTarget(routeSymbol.value))

watch(routeSymbol, (symbol) => {
  symbolDraft.value = symbol
})

function openDraftSymbol(): void {
  const symbol = normalizeStockSymbol(symbolDraft.value)
  if (!symbol) {
    return
  }
  void router.push({ name: 'stock-detail', params: { symbol } })
}

function goBack(): void {
  if (window.history.length > 1) {
    router.back()
    return
  }
  void router.push({ name: 'watchlist' })
}

function normalizeStockSymbol(value: string): string {
  const symbol = value.trim().toLowerCase()
  if (!symbol) {
    return ''
  }

  if (symbol.includes('.')) {
    const [code, suffix] = symbol.split('.', 2)
    if (suffix === 'sh') {
      return `sh${code}`
    }
    if (suffix === 'sz') {
      return `sz${code}`
    }
    if (suffix === 'bj') {
      return `bj${code}`
    }
  }

  if (symbol.startsWith('sh') || symbol.startsWith('sz') || symbol.startsWith('bj')) {
    return symbol
  }

  if (/^\d{6}$/.test(symbol)) {
    if (/^(300|301|000|001|002|003)/.test(symbol)) {
      return `sz${symbol}`
    }
    if (/^(600|601|603|605|688)/.test(symbol)) {
      return `sh${symbol}`
    }
    if (/^[48]/.test(symbol)) {
      return `bj${symbol}`
    }
  }

  return symbol
}

function buildStockDetailTarget(rawSymbol: string): StockDetailTarget {
  const symbol = normalizeStockSymbol(rawSymbol)
  const prefix = symbol.slice(0, 2)
  const code = symbol.slice(2)
  const market = prefix === 'sh' ? '1' : '0'
  const secid = `${market}.${code}`
  const isIndex = symbol.startsWith('sh000') || symbol.startsWith('sz399')
  const url = isIndex
    ? `${eastMoneyHost}/basic/full.html?mcid=${secid}`
    : `${eastMoneyHost}/basic/h5chart-iframe.html?code=${code}&market=${market}`

  return {
    symbol,
    code,
    market,
    secid,
    url,
    fallbackUrl: `${eastMoneyHost}/${symbol}.html`,
    isIndex,
  }
}
</script>
