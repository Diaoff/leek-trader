import { defineStore } from 'pinia'

export const useAppStore = defineStore('app', {
  state: () => ({
    appName: 'Leek Trader',
    modules: ['行情', '策略', '模拟交易', '持仓分析'],
    sidebar: {
      opened: true,
    },
    theme: {
      dark: true,
    },
  }),
  actions: {
    toggleSidebar() {
      this.sidebar.opened = !this.sidebar.opened
    },
    setTheme(dark: boolean) {
      this.theme.dark = dark
    },
  },
})
