<template>
  <div class="app-shell">
    <aside class="app-sidebar">
      <div class="brand-block">
        <p class="brand-kicker">Leek Trader</p>
        <h1 class="brand-title">股票模拟交易 MVP</h1>
        <p class="brand-subtitle">单用户、本地运行、主链路优先。</p>
      </div>

      <el-menu :default-active="activeMenu" class="app-menu" router>
        <el-menu-item index="/">
          <el-icon><HomeFilled /></el-icon>
          <span>仪表盘</span>
        </el-menu-item>
        <el-menu-item index="/market">
          <el-icon><TrendCharts /></el-icon>
          <span>行情</span>
        </el-menu-item>
        <el-menu-item index="/strategies">
          <el-icon><Setting /></el-icon>
          <span>策略</span>
        </el-menu-item>
        <el-menu-item index="/portfolio">
          <el-icon><Document /></el-icon>
          <span>交易与持仓</span>
        </el-menu-item>
      </el-menu>
    </aside>

    <div class="app-main">
      <header class="app-header">
        <div>
          <div class="header-title">主链路演示台</div>
          <div class="header-subtitle">
            API：
            <code>{{ apiBaseUrl }}</code>
          </div>
        </div>

        <div class="header-actions">
          <el-tag :type="healthTagType" effect="dark">
            {{ healthLabel }}
          </el-tag>
          <span class="header-meta">环境：{{ health.environment ?? 'unknown' }}</span>
          <span class="header-meta">租户：{{ health.tenant ?? 'unknown' }}</span>
          <el-button text @click="refreshHealth">刷新状态</el-button>
          <el-button text tag="a" href="http://localhost:8000/docs" target="_blank">
            API 文档
          </el-button>
        </div>
      </header>

      <main class="app-content">
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
</template>

<script setup lang="ts">
import { computed, onMounted, reactive } from 'vue'
import { useRoute } from 'vue-router'
import { Document, HomeFilled, Setting, TrendCharts } from '@element-plus/icons-vue'

import { fetchHealth, type HealthResponse } from './api/health'
import { getApiErrorMessage } from './utils/http'

const route = useRoute()
const activeMenu = computed(() => route.path)
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'

const health = reactive<Partial<HealthResponse>>({
  status: 'loading',
})
const healthError = computed(() => health.status === 'error' ? '后端健康检查失败，请确认本地服务已经启动。' : '')
const healthLabel = computed(() => {
  if (health.status === 'ok') {
    return '后端正常'
  }
  if (health.status === 'loading') {
    return '检查中'
  }
  return '后端未就绪'
})
const healthTagType = computed(() => {
  if (health.status === 'ok') {
    return 'success'
  }
  if (health.status === 'loading') {
    return 'info'
  }
  return 'danger'
})

onMounted(() => {
  void refreshHealth()
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
