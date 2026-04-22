<template>
  <el-tag class="pill-tag" :type="type">
    {{ label }}
  </el-tag>
</template>

<script setup lang="ts">
interface Props {
  label: string
  type: 'success' | 'warning' | 'danger' | 'info'
}

defineProps<Props>()
</script>
