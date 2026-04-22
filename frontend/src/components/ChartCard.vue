<template>
  <el-card v-if="show" class="surface-card">
    <template #header>
      <div class="flex items-center justify-between gap-4">
        <span class="font-semibold">{{ title }}</span>
        <el-button v-if="refreshable" text :loading="loading" @click="handleRefresh">
          {{ refreshText || '刷新' }}
        </el-button>
      </div>
    </template>

    <div ref="chartContainer" v-loading="loading" class="chart-container"></div>
  </el-card>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

interface Props {
  show?: boolean
  title: string
  refreshable?: boolean
  refreshText?: string
  loading?: boolean
  height?: string
}

const props = withDefaults(defineProps<Props>(), {
  show: true,
  refreshable: false,
  refreshText: '刷新',
  loading: false,
  height: 'h-72',
})

const emit = defineEmits<{
  (e: 'refresh'): void
}>()

const chartContainer = ref<HTMLDivElement>()
let chartInstance: { dispose: () => void; resize: () => void; setOption: (option: object) => void } | null = null
let echartsModule: { init: (element: HTMLDivElement) => typeof chartInstance } | null = null

async function initChart(): Promise<void> {
  if (!chartContainer.value) {
    return
  }

  if (!echartsModule) {
    const [{ init, use }, { LineChart }, { GridComponent, TooltipComponent }, { CanvasRenderer }] = await Promise.all([
      import('echarts/core'),
      import('echarts/charts'),
      import('echarts/components'),
      import('echarts/renderers'),
    ])
    use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])
    echartsModule = { init }
  }

  if (!chartInstance) {
    chartInstance = echartsModule.init(chartContainer.value)
  }
}

function setOption(option: object): void {
  chartInstance?.setOption(option)
}

function handleResize(): void {
  chartInstance?.resize()
}

function handleRefresh(): void {
  emit('refresh')
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chartInstance?.dispose()
  chartInstance = null
})

defineExpose({
  initChart,
  setOption,
})
</script>

<style scoped>
.chart-container {
  width: 100%;
}
</style>
