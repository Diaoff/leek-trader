<template>
  <div :class="['app-shell', { 'sidebar-collapsed': !appStore.sidebar.opened }]">
    <aside class="app-sidebar">
      <div class="brand-block">
        <p class="brand-kicker">Cold Data Desk</p>
        <h1 class="brand-title">Leek Trader</h1>
        <p class="brand-subtitle">
          面向股票模拟交易的冷峻数据仪表盘，聚焦账户、风险、挂单与策略状态。
        </p>
      </div>

      <nav class="app-nav" aria-label="主导航">
        <button
          v-for="item in navItems"
          :key="item.name"
          :class="['nav-link', { active: route.name === item.name }]"
          @click="router.push(item.path)"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path :d="item.icon" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <span class="nav-copy">
            <strong>{{ item.label }}</strong>
            <small>{{ item.caption }}</small>
          </span>
        </button>
      </nav>

      <div class="sidebar-panel">
        <div class="sidebar-panel-label">系统脉冲</div>
        <div class="sidebar-stat">
          <span>服务状态</span>
          <span :class="['status-chip', healthToneClass]">{{ healthLabel }}</span>
        </div>
        <div class="sidebar-stat">
          <span>环境</span>
          <span class="mono-data">{{ health.environment ?? 'unknown' }}</span>
        </div>
        <div class="sidebar-stat">
          <span>租户</span>
          <span class="mono-data">{{ health.tenant ?? 'unknown' }}</span>
        </div>
        <div class="sidebar-stat">
          <span>接口</span>
          <span class="mono-data">{{ apiHost }}</span>
        </div>
      </div>
    </aside>

    <div class="app-main">
      <header v-if="showAppHeader" class="app-header">
        <div>
          <div v-if="currentPage.eyebrow" class="header-kicker">{{ currentPage.eyebrow }}</div>
          <div class="header-title">{{ currentPage.title }}</div>
          <div v-if="currentPage.subtitle" class="header-subtitle">{{ currentPage.subtitle }}</div>
        </div>

        <div class="header-actions">
          <span class="status-chip subtle">{{ serviceSummary }}</span>
          <span :class="['status-chip', healthToneClass]">{{ healthLabel }}</span>
          <button class="secondary-button" type="button" @click="appStore.toggleSidebar()">
            {{ appStore.sidebar.opened ? '收起侧栏' : '展开侧栏' }}
          </button>
          <button class="primary-button" type="button" @click="refreshHealth">
            刷新健康检查
          </button>
        </div>
      </header>

      <main class="app-content">
        <ErrorAlert :message="healthError" type="warning" />
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import ErrorAlert from './components/ErrorAlert.vue'
import { fetchHealth, type HealthResponse } from './api/health'
import { useAppStore } from './stores/app'
import { getApiErrorMessage } from './utils/http'

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'

const health = reactive<Partial<HealthResponse>>({
  status: 'loading',
  environment: 'unknown',
  tenant: 'unknown',
  services: {
    api: 'unknown',
    database: 'unknown',
    redis: 'unknown',
  },
})

const navItems = [
  {
    name: 'dashboard',
    label: '总览',
    caption: '资金与风险面',
    path: '/',
    icon: 'M3 12h7V4H3zm0 8h7v-6H3zm11 0h7V12h-7zm0-16v6h7V4z',
  },
  {
    name: 'watchlist',
    label: '盯盘',
    caption: '自选与报价',
    path: '/watchlist',
    icon: 'M4 5h16M4 12h16M4 19h10m3-8 3-3m0 0-3-3m3 3H9',
  },
  {
    name: 'ai',
    label: 'AI',
    caption: '模型与研判',
    path: '/ai',
    icon: 'M12 3l2.4 4.86L20 8.67l-4 3.9.94 5.51L12 15.47 7.06 18.08 8 12.57 4 8.67l5.6-.81z',
  },
  {
    name: 'strategies',
    label: '策略',
    caption: '信号与配置',
    path: '/strategies',
    icon: 'M4 19h16M6 15l4-4 3 3 5-7',
  },
  {
    name: 'portfolio',
    label: '交易',
    caption: '下单与持仓',
    path: '/portfolio',
    icon: 'M4 7h16M7 12h10M10 17h4',
  },
  {
    name: 'analysis',
    label: '复盘',
    caption: '收益与回撤',
    path: '/analysis',
    icon: 'M4 19V5m0 14 5-5 4 3 7-9',
  },
]

const pageMeta: Record<string, { eyebrow: string; title: string; subtitle: string }> = {
  dashboard: {
    eyebrow: 'Desk Overview',
    title: '总览驾驶舱',
    subtitle: '用一屏追踪资金、风险、活跃策略和最新订单状态。',
  },
  watchlist: {
    eyebrow: '',
    title: '自选盯盘台',
    subtitle: '自选、分组、行情与快捷操作。',
  },
  strategies: {
    eyebrow: 'Signal Engine',
    title: '策略中心',
    subtitle: '对内置策略的启停状态、最新信号和参数结构做统一观察。',
  },
  portfolio: {
    eyebrow: 'Execution Desk',
    title: '交易与持仓',
    subtitle: '在同一工作台内处理下单、挂单撮合、持仓和委托队列。',
  },
  analysis: {
    eyebrow: 'Performance Review',
    title: '盈亏复盘',
    subtitle: '围绕收益曲线、月度统计和风险指标做交易结果回看。',
  },
  ai: {
    eyebrow: 'AI Research',
    title: 'AI 分析',
    subtitle: '连接自定义大模型，对个股和问题做结构化研判。',
  },
}

const currentPage = computed(() => pageMeta[String(route.name ?? 'dashboard')] ?? pageMeta.dashboard)
const showAppHeader = computed(() => route.name === 'dashboard')

const healthError = computed(() =>
  health.status === 'error' ? '后端健康检查失败，请确认本地服务已经启动。' : '',
)

const healthLabel = computed(() => {
  if (health.status === 'ok') {
    return '在线'
  }
  if (health.status === 'loading') {
    return '检测中'
  }
  return '异常'
})

const healthToneClass = computed(() => {
  if (health.status === 'ok') {
    return 'positive'
  }
  if (health.status === 'loading') {
    return 'neutral'
  }
  return 'negative'
})

const serviceSummary = computed(() => {
  const services = health.services
  if (!services) {
    return 'api: unknown / db: unknown / redis: unknown'
  }
  return `api: ${services.api} / db: ${services.database} / redis: ${services.redis}`
})

const apiHost = computed(() => {
  try {
    return new URL(apiBaseUrl).host
  } catch {
    return apiBaseUrl
  }
})

async function refreshHealth(): Promise<void> {
  health.status = 'loading'
  try {
    const payload = await fetchHealth()
    Object.assign(health, payload)
  } catch (error: unknown) {
    Object.assign(health, {
      status: 'error',
      environment: 'unknown',
      tenant: 'unknown',
      services: {
        api: 'error',
        database: 'unknown',
        redis: 'unknown',
      },
      message: getApiErrorMessage(error, '健康检查失败'),
    })
  }
}

onMounted(() => {
  void refreshHealth()
})
</script>
