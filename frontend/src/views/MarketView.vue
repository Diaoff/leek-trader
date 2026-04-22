<template>
  <section class="flex flex-col gap-6">
    <div>
      <h2 class="text-2xl font-bold text-slate-900">行情中心</h2>
      <p class="text-slate-500">展示 `/api/v1/quotes` 返回的实时行情快照。</p>
    </div>

    <el-card>
      <el-table :data="quotes" stripe>
        <el-table-column prop="symbol" label="代码" min-width="140" />
        <el-table-column prop="price" label="现价" min-width="120" />
        <el-table-column prop="change_percent" label="涨跌幅(%)" min-width="140" />
        <el-table-column prop="volume" label="成交量" min-width="140" />
        <el-table-column prop="timestamp" label="时间" min-width="220" />
      </el-table>
    </el-card>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchQuotes } from '../api/quotes'

const quotes = ref<Array<Record<string, string | number | boolean>>>([])

onMounted(async () => {
  quotes.value = await fetchQuotes()
})
</script>
