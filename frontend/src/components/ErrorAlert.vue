<template>
  <el-alert
    v-if="message"
    :closable="false"
    :title="message"
    :type="type"
    show-icon
  />
</template>

<script setup lang="ts">
interface Props {
  message: string
  type?: 'warning' | 'error' | 'success' | 'info'
}

withDefaults(defineProps<Props>(), {
  type: 'warning',
})
</script>
