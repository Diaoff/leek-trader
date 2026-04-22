import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        'dark-bg': '#1a1a1a',
        'dark-card': '#252525',
        'dark-border': '#333333',
        'dark-text': '#e0e0e0',
        'dark-text-secondary': '#a0a0a0',
        'success': '#4caf50',
        'warning': '#ff9800',
        'danger': '#f44336',
        'info': '#2196f3',
        'primary': '#1890ff',
      },
    },
  },
  plugins: [],
} satisfies Config
