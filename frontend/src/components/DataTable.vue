<template>
  <el-table
    v-loading="loading"
    :data="data"
    :stripe="stripe"
    :empty-text="emptyText"
  >
    <slot />
  </el-table>
</template>

<script setup lang="ts">
interface Props {
  data: unknown[]
  loading?: boolean
  stripe?: boolean
  emptyText?: string
}

withDefaults(defineProps<Props>(), {
  loading: false,
  stripe: true,
  emptyText: '暂无数据',
})
</script>
