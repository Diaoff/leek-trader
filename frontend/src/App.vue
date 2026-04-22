<template>
  <el-config-provider>
    <div class="dark">
      <el-container class="min-h-screen bg-dark-bg text-dark-text">
        <el-aside width="200px" class="bg-dark-card border-r border-dark-border">
          <div class="p-4 border-b border-dark-border">
            <h1 class="text-xl font-bold text-primary">生活助手调度系统</h1>
            <p class="text-sm text-dark-text-secondary">韭菜看板</p>
          </div>
          <el-menu
            mode="vertical"
            :default-active="activeMenu"
            class="bg-dark-card border-r-0"
            router
          >
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
              <span>持仓</span>
            </el-menu-item>
          </el-menu>
        </el-aside>
        <el-container>
          <el-header class="flex items-center justify-between gap-6 border-b border-dark-border bg-dark-card">
            <div class="flex items-center gap-4">
              <el-tag type="success" size="small">运行中</el-tag>
              <span class="text-sm text-dark-text-secondary">PID: 2832 | 运行时间: 172.34s</span>
            </div>
            <div class="flex items-center gap-4">
              <span class="text-sm">刷新</span>
              <span class="text-sm">1723456789</span>
              <span class="text-sm">停止自动刷新</span>
            </div>
          </el-header>
          <el-main class="p-4">
            <router-view />
          </el-main>
        </el-container>
      </el-container>
    </div>
  </el-config-provider>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { HomeFilled, TrendCharts, Setting, Document } from '@element-plus/icons-vue'

const route = useRoute()
const activeMenu = computed(() => route.path)
</script>

<style scoped>
.el-aside {
  height: 100vh;
  position: fixed;
  left: 0;
  top: 0;
  overflow-y: auto;
}

.el-container {
  margin-left: 200px;
}

.el-header {
  padding: 0 20px;
}

.el-main {
  padding: 20px;
}
</style>
