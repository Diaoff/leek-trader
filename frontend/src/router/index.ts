import { createRouter, createWebHistory } from 'vue-router'

import DashboardView from '../views/DashboardView.vue'
import MarketView from '../views/MarketView.vue'
import PortfolioView from '../views/PortfolioView.vue'
import StrategiesView from '../views/StrategiesView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: DashboardView,
    },
    {
      path: '/market',
      name: 'market',
      component: MarketView,
    },
    {
      path: '/strategies',
      name: 'strategies',
      component: StrategiesView,
    },
    {
      path: '/portfolio',
      name: 'portfolio',
      component: PortfolioView,
    },
  ],
})
