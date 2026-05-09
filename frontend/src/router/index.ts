import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { title: '登录', public: true },
    },
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
      path: '/stocks/:symbol?',
      name: 'stock-detail',
      component: () => import('../views/StockDetailView.vue'),
      meta: { title: '个股详情' },
    },
    {
      path: '/news',
      redirect: { name: 'dashboard' },
    },
    {
      path: '/market',
      redirect: { name: 'dashboard' },
    },
    {
      path: '/smart-selection',
      name: 'smart-selection',
      component: () => import('../views/SmartSelectionView.vue'),
      meta: { title: '智能选股' },
    },
    {
      path: '/strategies',
      name: 'strategies',
      component: () => import('../views/StrategiesView.vue'),
      meta: { title: '策略管理' },
    },
    {
      path: '/rl-training',
      name: 'rl-training',
      component: () => import('../views/RLTrainingView.vue'),
      meta: { title: 'RL 训练' },
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
    {
      path: '/settings',
      name: 'settings',
      component: () => import('../views/SettingsView.vue'),
      meta: { title: '偏好设置' },
    },
  ],
})

router.beforeEach((to) => {
  if (to.meta.title) {
    document.title = `${to.meta.title} - Leek Trader`
  }
  if (!to.meta.public && !localStorage.getItem('token')) {
    return { name: 'login' }
  }
})

export { router }
