<template>
  <el-card class="surface-card metric-card">
    <div class="metric-label">{{ label }}</div>
    <div class="metric-value" :class="emphasisClass">{{ value }}</div>
    <div class="metric-hint">{{ hint }}</div>
  </el-card>
</template>

<script setup lang="ts">
interface Props {
  label: string
  value: string | number
  hint?: string
  emphasisClass?: string
}

withDefaults(defineProps<Props>(), {
  hint: '',
  emphasisClass: '',
})
</script>
