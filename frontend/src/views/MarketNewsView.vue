<template>
  <div class="space-y-6">
    <section class="panel">
      <div class="panel-header flex-wrap">
        <div>
          <div class="section-label">Market Flash</div>
          <h1 class="page-title mt-3">市场快讯</h1>
          <p class="page-subtitle">默认展示选股宝时间流；输入股票名或代码后刷新九研讨论与三源摘要，不触发 AI 分析。</p>
        </div>
        <button class="secondary-button" type="button" :disabled="loading" @click="refreshAll">
          {{ loading ? '刷新中...' : '刷新' }}
        </button>
      </div>

      <div class="grid gap-3 md:grid-cols-3">
        <div v-for="status in sourceStatuses" :key="status.source" class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
          <div class="flex items-center justify-between gap-3">
            <span class="font-semibold">{{ status.label }}</span>
            <span :class="['status-chip', status.tone]">{{ status.text }}</span>
          </div>
          <p class="mt-3 text-sm text-[var(--text-secondary)]">{{ status.hint }}</p>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto_auto]">
        <label>
          <span class="field-label">股票名 / 代码</span>
          <input
            v-model.trim="keyword"
            class="field-input"
            type="search"
            placeholder="例如：宁德时代 / 300750"
            @keyup.enter="runSearch"
          />
        </label>
        <button class="primary-button self-end" type="button" :disabled="loading || !keyword" @click="runSearch">搜索九研</button>
        <button class="ghost-button self-end" type="button" :disabled="loading" @click="clearSearch">清空</button>
      </div>
      <div v-if="errors.length" class="mt-4 flex flex-wrap gap-2">
        <span v-for="error in errors" :key="error" class="status-chip negative">{{ error }}</span>
      </div>
    </section>

    <section class="grid gap-4 xl:grid-cols-3">
      <NewsColumn title="市场快讯" subtitle="选股宝时间流" :items="marketItems" empty-text="暂无选股宝快讯" />
      <NewsColumn title="个股讨论" subtitle="九研文章搜索" :items="discussionItems" :empty-text="keyword ? '暂无九研搜索结果' : '输入股票名或代码后展示九研文章'" />
      <NewsColumn title="关注动态" subtitle="雪球配置用户" :items="xueqiuItems" :empty-text="xueqiuEmptyText" />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, ref } from 'vue'

import { fetchMarketNews, fetchNewsBrief, fetchXueqiuNews } from '../api/news'
import type { NewsItem } from '../types/news'
import { getApiErrorMessage } from '../utils/http'

const keyword = ref('')
const loading = ref(false)
const marketItems = ref<NewsItem[]>([])
const discussionItems = ref<NewsItem[]>([])
const xueqiuItems = ref<NewsItem[]>([])
const errors = ref<string[]>([])

const xueqiuUnconfigured = computed(() => errors.value.includes('雪球未配置'))
const xueqiuEmptyText = computed(() => (xueqiuUnconfigured.value ? '雪球未配置：请在环境变量中设置 XUEQIU_USER_IDS' : '暂无雪球动态'))

const sourceStatuses = computed(() => [
  {
    source: 'xuangubao',
    label: '选股宝',
    text: marketItems.value.length ? `${marketItems.value.length} 条` : '待更新',
    tone: marketItems.value.length ? 'positive' : 'neutral',
    hint: '市场快讯默认加载，适合观察盘中情绪。',
  },
  {
    source: 'jiuyangongshe',
    label: '九研',
    text: keyword.value ? `${discussionItems.value.length} 条` : '待搜索',
    tone: discussionItems.value.length ? 'positive' : 'neutral',
    hint: '按股票名或代码检索个股讨论文章。',
  },
  {
    source: 'xueqiu',
    label: '雪球',
    text: xueqiuUnconfigured.value ? '未配置' : `${xueqiuItems.value.length} 条`,
    tone: xueqiuUnconfigured.value ? 'negative' : xueqiuItems.value.length ? 'positive' : 'neutral',
    hint: '通过后端环境变量配置关注用户 ID 和可选 Cookie。',
  },
])

async function refreshAll(): Promise<void> {
  loading.value = true
  errors.value = []
  try {
    if (keyword.value) {
      const payload = await fetchNewsBrief(keyword.value, 10)
      marketItems.value = payload.market
      discussionItems.value = payload.discussions
      xueqiuItems.value = payload.xueqiu
      errors.value = payload.errors
    } else {
      const [market, xueqiu] = await Promise.all([fetchMarketNews(20), fetchXueqiuNews(20)])
      marketItems.value = market.items
      discussionItems.value = []
      xueqiuItems.value = xueqiu.items
      errors.value = [...market.errors, ...xueqiu.errors]
    }
  } catch (error: unknown) {
    errors.value = [getApiErrorMessage(error, '市场快讯刷新失败')]
  } finally {
    loading.value = false
  }
}

async function runSearch(): Promise<void> {
  if (!keyword.value) {
    return
  }
  await refreshAll()
}

async function clearSearch(): Promise<void> {
  keyword.value = ''
  discussionItems.value = []
  await refreshAll()
}

function formatTime(value: string | null): string {
  if (!value) {
    return '时间未知'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value.slice(0, 16)
  }
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

const NewsColumn = defineComponent({
  props: {
    title: { type: String, required: true },
    subtitle: { type: String, required: true },
    items: { type: Array as () => NewsItem[], required: true },
    emptyText: { type: String, required: true },
  },
  setup(props) {
    return () => h('div', { class: 'panel min-h-[420px]' }, [
      h('div', { class: 'panel-header' }, [
        h('div', [
          h('div', { class: 'section-label' }, props.subtitle),
          h('h2', { class: 'panel-title mt-3' }, props.title),
        ]),
        h('span', { class: 'status-chip subtle' }, `${props.items.length} 条`),
      ]),
      props.items.length === 0
        ? h('div', { class: 'compact-empty' }, props.emptyText)
        : h('div', { class: 'space-y-3' }, props.items.map((item) => h('article', { key: item.id, class: 'rounded-[18px] border border-white/5 bg-white/[0.03] p-4' }, [
          h('div', { class: 'mb-2 flex items-center justify-between gap-3 text-xs text-[var(--text-tertiary)]' }, [
            h('span', { class: 'mono-data' }, formatTime(item.published_at)),
            item.author ? h('span', item.author) : null,
          ]),
          item.url
            ? h('a', { class: 'font-semibold leading-6 hover:text-[var(--accent)]', href: item.url, target: '_blank', rel: 'noreferrer' }, item.title)
            : h('div', { class: 'font-semibold leading-6' }, item.title),
          item.summary && item.summary !== item.title
            ? h('p', { class: 'mt-2 line-clamp-3 text-sm leading-6 text-[var(--text-secondary)]' }, item.summary)
            : null,
        ]))),
    ])
  },
})

onMounted(() => {
  void refreshAll()
})
</script>
