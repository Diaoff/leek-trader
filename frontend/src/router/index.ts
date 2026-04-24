import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: () => import('../views/DashboardView.vue'),
      meta: { title: '仪表盘' },
    },
    {
      path: '/watchlist',
      name: 'watchlist',
      component: () => import('../views/WatchlistView.vue'),
      meta: { title: '自选股' },
    },
    {
      path: '/market',
      name: 'market',
      component: () => import('../views/MarketOverviewView.vue'),
      meta: { title: '市场研究入口' },
    },
    {
      path: '/market/research',
      name: 'market-research',
      component: () => import('../views/MarketResearchReportView.vue'),
      meta: { title: '研究报告' },
    },
    {
      path: '/strategies',
      name: 'strategies',
      component: () => import('../views/StrategiesView.vue'),
      meta: { title: '策略管理' },
    },
    {
      path: '/portfolio',
      name: 'portfolio',
      component: () => import('../views/PortfolioView.vue'),
      meta: { title: '交易与持仓' },
    },
    {
      path: '/analysis',
      name: 'analysis',
      component: () => import('../views/AnalysisView.vue'),
      meta: { title: '盈亏分析' },
    },
    {
      path: '/ai',
      name: 'ai',
      component: () => import('../views/AiAnalysisView.vue'),
      meta: { title: 'AI 分析' },
    },
  ],
})

router.beforeEach((to) => {
  if (to.meta.title) {
    document.title = `${to.meta.title} - Leek Trader`
  }
})

export { router }
