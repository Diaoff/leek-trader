<template>
  <div class="min-h-screen bg-dark">
    <canvas id="particles-bg" class="fixed inset-0 z-0 opacity-30"></canvas>
    
    <div class="relative z-10">
      <header class="border-b border-dark-border bg-dark-secondary/80 backdrop-blur-sm sticky top-0 z-20">
        <div class="container mx-auto px-4 py-4 flex justify-between items-center">
          <div class="flex items-center">
            <div class="h-10 w-10 bg-blue-600 flex items-center justify-center mr-3">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
              </svg>
            </div>
            <h1 class="text-2xl font-bold tracking-tight">股票模拟交易系统</h1>
          </div>
          <div class="flex items-center space-x-4">
            <div class="relative">
              <input 
                type="text" 
                placeholder="搜索股票..." 
                class="bg-dark border border-dark-border pl-10 pr-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 w-64 rounded-none"
                v-model="searchQuery"
                @input="handleSearch"
              >
              <svg xmlns="http://www.w3.org/2000/svg" class="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            <button class="p-2 bg-dark border border-dark-border hover:bg-dark-card transition-colors rounded-none">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </button>
          </div>
        </div>
      </header>

      <div class="container mx-auto px-4 py-6">
        <div class="flex">
          <aside class="w-64 mr-8">
            <nav class="space-y-1">
              <div 
                v-for="item in navItems" 
                :key="item.id"
                :class="['nav-item', item.id === activeTab ? 'active' : '']"
                class="p-3 flex items-center cursor-pointer"
                @click="switchTab(item.id)"
              >
                <component :is="item.icon" class="w-5 h-5 mr-3" />
                <span>{{ item.label }}</span>
              </div>
            </nav>

            <div class="mt-8 p-4 bg-dark-secondary border border-dark-border">
              <h3 class="text-sm font-medium text-gray-400 mb-3">市场状态</h3>
              <div class="space-y-3">
                <div class="flex justify-between items-center" v-for="market in marketStatus" :key="market.name">
                  <span class="text-sm">{{ market.name }}</span>
                  <div class="flex items-center">
                    <span class="font-medium">{{ market.price }}</span>
                    <span :class="['ml-2 text-xs', market.change >= 0 ? 'text-green-400' : 'text-red-400']">
                      {{ market.change >= 0 ? '+' : '' }}{{ market.change }}%
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </aside>

          <main class="flex-1">
            <el-alert
              v-if="healthError"
              :closable="false"
              type="warning"
              :title="healthError"
              show-icon
              class="mb-4"
            />
            <router-view />
          </main>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive, h } from 'vue'
import { useRouter } from 'vue-router'

import { fetchHealth, type HealthResponse } from './api/health'
import { getApiErrorMessage } from './utils/http'

const router = useRouter()
const activeTab = ref('dashboard')
const searchQuery = ref('')
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'

const health = reactive<Partial<HealthResponse>>({
  status: 'loading',
})
const healthError = computed(() => health.status === 'error' ? '后端健康检查失败，请确认本地服务已经启动。' : '')

const DashboardIcon = () => h('svg', {
  xmlns: 'http://www.w3.org/2000/svg',
  fill: 'none',
  viewBox: '0 0 24 24',
  stroke: 'currentColor',
  class: 'w-5 h-5'
}, [
  h('path', {
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'stroke-width': '2',
    d: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z'
  })
])



const StrategiesIcon = () => h('svg', {
  xmlns: 'http://www.w3.org/2000/svg',
  fill: 'none',
  viewBox: '0 0 24 24',
  stroke: 'currentColor',
  class: 'w-5 h-5'
}, [
  h('path', {
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'stroke-width': '2',
    d: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01'
  })
])

const PortfolioIcon = () => h('svg', {
  xmlns: 'http://www.w3.org/2000/svg',
  fill: 'none',
  viewBox: '0 0 24 24',
  stroke: 'currentColor',
  class: 'w-5 h-5'
}, [
  h('path', {
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'stroke-width': '2',
    d: 'M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4'
  })
])

const AnalysisIcon = () => h('svg', {
  xmlns: 'http://www.w3.org/2000/svg',
  fill: 'none',
  viewBox: '0 0 24 24',
  stroke: 'currentColor',
  class: 'w-5 h-5'
}, [
  h('path', {
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'stroke-width': '2',
    d: 'M13 7h8m0 0v8m0-8l-8 8-4-4-6 6'
  })
])

const WatchlistIcon = () => h('svg', {
  xmlns: 'http://www.w3.org/2000/svg',
  fill: 'none',
  viewBox: '0 0 24 24',
  stroke: 'currentColor',
  class: 'w-5 h-5'
}, [
  h('path', {
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'stroke-width': '2',
    d: 'M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z'
  })
])

const navItems = [
  { id: 'dashboard', label: '仪表盘', icon: DashboardIcon },
  { id: 'watchlist', label: '自选股', icon: WatchlistIcon },
  { id: 'strategies', label: '策略管理', icon: StrategiesIcon },
  { id: 'portfolio', label: '交易与持仓', icon: PortfolioIcon },
  { id: 'analysis', label: '盈亏分析', icon: AnalysisIcon }
]

const marketStatus = ref([
  { name: '上证指数', price: '3,258.63', change: -0.82 },
  { name: '深证成指', price: '10,825.93', change: 0.45 },
  { name: '创业板指', price: '2,156.78', change: 1.23 }
])

const switchTab = (tabId: string) => {
  activeTab.value = tabId
  switch (tabId) {
    case 'dashboard':
      router.push('/')
      break
    case 'watchlist':
      router.push('/watchlist')
      break
    case 'strategies':
      router.push('/strategies')
      break
    case 'portfolio':
      router.push('/portfolio')
      break
    case 'analysis':
      router.push('/analysis')
      break
  }
}

const handleSearch = () => {
  console.log('搜索:', searchQuery.value)
}

const initParticles = () => {
  const canvas = document.getElementById('particles-bg')
  if (!canvas) return
  
  const ctx = canvas.getContext('2d')
  
  canvas.width = window.innerWidth
  canvas.height = window.innerHeight
  
  const particles: any[] = []
  const particleCount = 100
  
  for (let i = 0; i < particleCount; i++) {
    particles.push({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      radius: Math.random() * 2 + 1,
      color: `rgba(${Math.floor(Math.random()*80+180)}, ${Math.floor(Math.random()*80+180)}, ${Math.floor(Math.random()*80+180)}, 0.5)`,
      speedX: Math.random() * 0.5 - 0.25,
      speedY: Math.random() * 0.5 - 0.25
    })
  }
  
  let mouseX = 0, mouseY = 0
  document.addEventListener('mousemove', (e) => {
    mouseX = e.clientX
    mouseY = e.clientY
  })
  
  function animate() {
    requestAnimationFrame(animate)
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    
    particles.forEach(p => {
      p.x += p.speedX
      p.y += p.speedY
      
      if (p.x > canvas.width) p.x = 0
      if (p.x < 0) p.x = canvas.width
      if (p.y > canvas.height) p.y = 0
      if (p.y < 0) p.y = canvas.height
      
      const dx = p.x - mouseX
      const dy = p.y - mouseY
      const dist = Math.sqrt(dx * dx + dy * dy)
      if (dist < 100) {
        p.x += dx * 0.01
        p.y += dy * 0.01
      }
      
      ctx.beginPath()
      ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2)
      ctx.fillStyle = p.color
      ctx.fill()
    })
    
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x
        const dy = particles[i].y - particles[j].y
        const dist = Math.sqrt(dx * dx + dy * dy)
        
        if (dist < 120) {
          ctx.beginPath()
          ctx.strokeStyle = `rgba(59, 130, 246, ${0.2 * (1 - dist/120)})`
          ctx.lineWidth = 0.5
          ctx.moveTo(particles[i].x, particles[i].y)
          ctx.lineTo(particles[j].x, particles[j].y)
          ctx.stroke()
        }
      }
    }
  }
  
  animate()
  
  window.addEventListener('resize', () => {
    canvas.width = window.innerWidth
    canvas.height = window.innerHeight
  })
}

onMounted(() => {
  void refreshHealth()
  initParticles()
})

async function refreshHealth(): Promise<void> {
  try {
    const payload = await fetchHealth()
    Object.assign(health, payload)
  } catch (error) {
    Object.assign(health, {
      status: 'error',
      environment: 'unknown',
      tenant: 'unknown',
      message: getApiErrorMessage(error, '健康检查失败'),
    })
  }
}
</script>

<style scoped>
.bg-dark {
  background-color: #0f172a;
  color: #e2e8f0;
}

.bg-dark-secondary {
  background-color: #1e293b;
}

.bg-dark-card {
  background-color: #2a3a50;
}

.border-dark-border {
  border-color: #334155;
}

.nav-item {
  transition: all 0.2s ease;
  border-radius: 4px;
}

.nav-item:hover {
  background-color: #1e293b;
}

.nav-item.active {
  background-color: #3b82f6;
  color: white;
}

.sharp-btn {
  border-radius: 0;
}

.sharp-card {
  border-radius: 0;
}

.animate-fadeIn {
  animation: fadeIn 0.5s ease-in-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
