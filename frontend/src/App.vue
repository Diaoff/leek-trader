<template>
  <div :class="['app-shell', { 'sidebar-collapsed': showAppChrome && !appStore.sidebar.opened, 'auth-only': !showAppChrome }]">
    <aside v-if="showAppChrome" class="app-sidebar">
      <div class="brand-block">
        <p class="brand-kicker">Cold Data Desk</p>
        <h1 class="brand-title">Leek Trader</h1>
        <p class="brand-subtitle">
        </p>
      </div>

      <nav class="app-nav" aria-label="主导航">
        <button
          v-for="item in primaryNavItems"
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

        <div class="nav-group">
          <button
            :class="['nav-link nav-group-trigger', { active: moreNavActive }]"
            type="button"
            :aria-expanded="moreNavOpen"
            aria-controls="more-nav-items"
            @click="moreNavOpen = !moreNavOpen"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
              <path d="M4 7h16M4 12h16M4 17h16" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            <span class="nav-copy">
              <strong>更多</strong>
              <small>市场与分析</small>
            </span>
            <svg :class="['nav-chevron', { open: moreNavOpen }]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M6 9l6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </button>

          <div v-if="moreNavOpen" id="more-nav-items" class="nav-submenu">
            <button
              v-for="item in moreNavItems"
              :key="item.name"
              :class="['nav-link nav-sub-link', { active: route.name === item.name }]"
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
          </div>
        </div>
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
        <div v-if="showAuthControls" class="sidebar-session">
          <div class="sidebar-session-user">
            <span>当前用户</span>
            <strong>{{ currentUsername }}</strong>
          </div>
          <button class="secondary-button sidebar-logout" type="button" @click="logout">
            退出登录
          </button>
        </div>
      </div>
    </aside>

    <div class="app-main">
      <header v-if="showAppChrome && showAppHeader" class="app-header">
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
        <ErrorAlert v-if="showAppChrome" :message="healthError" type="warning" />
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import ErrorAlert from './components/ErrorAlert.vue'
import { fetchHealth, type HealthResponse } from './api/health'
import { useAppStore } from './stores/app'
import { useSessionStore } from './stores/session'
import { getApiErrorMessage } from './utils/http'

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()
const sessionStore = useSessionStore()
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

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

const primaryNavItems = [
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
]

const moreNavItems = [
  {
    name: 'stock-pool',
    label: '股票池',
    caption: '筛选与入池',
    path: '/stock-pool',
    icon: 'M4 6h16M6 12h12M9 18h6M8 6v12m8-12v12',
  },
  {
    name: 'smart-selection',
    label: '选股',
    caption: '日报与偏好',
    path: '/smart-selection',
    icon: 'M4 17l5-5 4 3 7-9M4 7h5m2 0h9m-5 12h5',
  },
  {
    name: 'rl-training',
    label: 'RL训练',
    caption: '模型与回测',
    path: '/rl-training',
    icon: 'M4 19h16M6 16V8m6 8V5m6 11v-6',
  },
  {
    name: 'analysis',
    label: '资产分析',
    caption: '收益与曲线',
    path: '/analysis',
    icon: 'M4 19h16M7 15l3-4 3 2 4-6m-9 12V9m5 10V7m5 12v-9',
  },
  {
    name: 'ai',
    label: 'AI',
    caption: '模型与研判',
    path: '/ai',
    icon: 'M12 3l2.4 4.86L20 8.67l-4 3.9.94 5.51L12 15.47 7.06 18.08 8 12.57 4 8.67l5.6-.81z',
  },
  {
    name: 'settings',
    label: '设置',
    caption: '费用与频率',
    path: '/settings',
    icon: 'M12 8a4 4 0 100 8 4 4 0 000-8zm8 4h2M2 12h2m14.14-6.14 1.42-1.42M4.22 19.78l1.42-1.42m12.72 0 1.42 1.42M4.22 4.22l1.42 1.42',
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
  'stock-detail': {
    eyebrow: 'Stock Detail',
    title: '个股详情',
    subtitle: '查看个股实时走势、盘口和东方财富详情页。',
  },
  'smart-selection': {
    eyebrow: 'Smart Selection',
    title: '智能选股',
    subtitle: '独立展示规则型选股日报、推荐清单和基础偏好状态。',
  },
  'stock-pool': {
    eyebrow: 'Stock Pool',
    title: '股票池筛选',
    subtitle: '按市场、关键词、标签和 ST 状态快速筛出候选并加入自选股。',
  },
  strategies: {
    eyebrow: 'Signal Engine',
    title: '策略中心',
    subtitle: '对内置策略的启停状态、最新信号和参数结构做统一观察。',
  },
  'rl-training': {
    eyebrow: 'RL Lab',
    title: 'RL 训练台',
    subtitle: '配置训练范围、生成日线强化学习模型并查看模型注册表。',
  },
  portfolio: {
    eyebrow: 'Execution Desk',
    title: '交易与持仓',
    subtitle: '在同一工作台内处理下单、挂单撮合、持仓和委托队列。',
  },
  analysis: {
    eyebrow: 'Performance Desk',
    title: '资产分析',
    subtitle: '查看收益指标、资金曲线、月度统计和交易表现。',
  },
  monitoring: {
    eyebrow: 'Operations Desk',
    title: '运行治理',
    subtitle: '查看核心运行指标、异步任务摘要、最新日志和系统健康。',
  },
  ai: {
    eyebrow: 'AI Research',
    title: 'AI 分析',
    subtitle: '连接自定义大模型，对个股和问题做结构化研判。',
  },
  settings: {
    eyebrow: 'Preferences',
    title: '偏好设置',
    subtitle: '集中管理模拟交易费用、智能选股参数和策略执行频率。',
  },
}

const currentPage = computed(() => pageMeta[String(route.name ?? 'dashboard')] ?? pageMeta.dashboard)
const showAppHeader = computed(() => route.name === 'dashboard' || route.name === 'monitoring')
const authToken = ref(localStorage.getItem('token'))
const showAppChrome = computed(() => route.name !== 'login' && Boolean(authToken.value))
const showAuthControls = computed(() => showAppChrome.value)
const currentUsername = computed(() => decodeTokenSubject(authToken.value) ?? '已登录用户')
const moreNavOpen = ref(false)
const moreNavActive = computed(() => moreNavItems.some((item) => item.name === route.name))

watch(
  moreNavActive,
  (active) => {
    if (active) {
      moreNavOpen.value = true
    }
  },
  { immediate: true },
)

watch(
  () => route.fullPath,
  () => {
    authToken.value = localStorage.getItem('token')
  },
)

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

function decodeTokenSubject(token: string | null): string | null {
  if (!token) {
    return null
  }
  try {
    const payload = JSON.parse(atob(token.split('.')[1] ?? '')) as { sub?: string }
    return payload.sub ?? null
  } catch {
    return null
  }
}

function logout(): void {
  localStorage.removeItem('token')
  authToken.value = null
  void router.replace('/login')
}

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
  void sessionStore.loadCurrentUser()
})
</script>
