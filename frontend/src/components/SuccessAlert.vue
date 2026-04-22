<template>
  <el-alert
    :closable="true"
    :title="message"
    type="success"
    show-icon
    @close="$emit('close')"
  />
</template>

<script setup lang="ts">
interface Props {
  message: string
}

defineProps<Props>()
defineEmits<{
  (e: 'close'): void
}>()
</script>
