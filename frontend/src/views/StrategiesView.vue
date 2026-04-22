<template>
  <section class="flex flex-col gap-6">
    <div>
      <h2 class="text-2xl font-bold text-slate-900">策略中心</h2>
      <p class="text-slate-500">展示策略参数与最近一次信号结果。</p>
    </div>

    <el-card>
      <el-table :data="strategies" stripe>
        <el-table-column prop="name" label="策略名称" min-width="180" />
        <el-table-column prop="strategy_type" label="类型" min-width="140" />
        <el-table-column prop="status" label="状态" min-width="120" />
        <el-table-column prop="latest_signal" label="最新信号" min-width="120" />
        <el-table-column prop="signal_symbol" label="标的" min-width="140" />
      </el-table>
    </el-card>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchStrategies } from '../api/strategies'

const strategies = ref<Array<Record<string, string | number | boolean | object>>>([])

onMounted(async () => {
  strategies.value = await fetchStrategies()
})
</script>
