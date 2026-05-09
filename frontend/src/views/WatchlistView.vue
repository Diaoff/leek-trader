<template>
  <section class="watchlist-page space-y-4">
    <section class="market-index-board" aria-label="市场指数实时看板">
      <div
        v-for="index in marketIndexes"
        :key="index.symbol"
        class="market-index-tile"
      >
        <div class="market-index-label">{{ index.label }}</div>
        <div class="market-index-value mono-data">
          {{ indexQuotes[index.symbol] ? formatIndexValue(indexQuotes[index.symbol].price) : '--' }}
        </div>
        <div :class="['market-index-change mono-data', marketToneClass(normalizeDailyChangePercent(indexQuotes[index.symbol]?.change_percent ?? 0))]">
          {{ indexQuotes[index.symbol] ? formatMarketChange(indexQuotes[index.symbol].change_percent) : '--' }}
        </div>
      </div>
    </section>

    <div class="watchlist-toolbar">
      <div class="toolbar-cluster">
        <button class="toolbar-button" type="button" :disabled="loading" @click="toggleSortMode">
          {{ sortMode ? '完成' : '排序' }}
        </button>
        <button class="toolbar-button" type="button" :disabled="loading" @click="refreshAll">
          刷新
        </button>
        <button class="toolbar-button accent" type="button" @click="searchOpen = true">
          搜索
        </button>
      </div>
      <div class="toolbar-cluster">
        <button class="toolbar-button" type="button" @click="createGroup">新建</button>
        <button class="toolbar-button" type="button" :disabled="!currentGroup || currentGroup.is_system" @click="renameGroup">改名</button>
        <button class="toolbar-button icon-button" type="button" :disabled="!canMoveGroupLeft" @click="moveGroup('left')" aria-label="左移">
          ←
        </button>
        <button class="toolbar-button icon-button" type="button" :disabled="!canMoveGroupRight" @click="moveGroup('right')" aria-label="右移">
          →
        </button>
        <button class="toolbar-button danger" type="button" :disabled="!canDeleteGroup" @click="deleteGroup">删除</button>
      </div>
    </div>

    <ErrorAlert :message="error" type="error" />

    <div class="panel">
      <div class="group-tabs">
        <button
          v-for="group in groups"
          :key="group.id"
          :class="['group-tab', { active: selectedGroupId === group.id }]"
          type="button"
          @click="selectGroup(group.id)"
        >
          <span>{{ group.name }}</span>
          <small>{{ group.item_count }}</small>
        </button>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <div>
          <h3 class="panel-title">行情主表</h3>
          <p class="panel-subtitle">展示价格、市值、成交量、当日涨跌、年初至今和备注操作。</p>
        </div>
        <div class="token-row">
          <span :class="['status-chip', streamConnected ? 'positive' : 'subtle']">{{ streamConnected ? '行情推送已连接' : '行情轮询兜底' }}</span>
          <span v-if="currentGroup" class="status-chip subtle">{{ currentGroup.name }}</span>
          <span v-if="sortMode" class="status-chip negative">拖拽排序已开启</span>
        </div>
      </div>

      <div v-if="rows.length === 0" class="empty-state">
        <div>{{ hasGroups ? '当前分组还没有自选股' : '当前还没有分组' }}</div>
        <div class="text-sm text-[var(--text-tertiary)]">
          {{ hasGroups ? '点击右上角“搜索添加”或从搜索面板一键加入当前分组。' : '先新建分组，或保留未分组自选后继续管理。' }}
        </div>
      </div>
      <div v-else class="table-shell">
        <table class="data-table watchlist-table">
          <thead>
            <tr>
              <th>股票标识</th>
              <th>实时价格</th>
              <th>总市值</th>
              <th>成交量</th>
              <th>当日涨跌</th>
              <th>年初至今</th>
              <th>备注 / 操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in rows"
              :key="row.id"
              :draggable="sortMode"
              :class="[{ 'row-dragging': draggingItemId === row.id }]"
              @dragstart="onDragStart(row)"
              @dragover.prevent="onDragOver(row)"
              @drop.prevent="onDrop(row)"
            >
              <td>
                <div class="stock-cell">
                  <div class="stock-main">
                    <span v-if="row.is_pinned" class="chip fixed">钉</span>
                    <span v-if="row.is_special_attention" class="chip focus">重点</span>
                    <span class="font-semibold">{{ row.security_name }}</span>
                  </div>
                  <div class="stock-subline">
                    <span class="mono-data">{{ row.security_code }}</span>
                    <span class="chip market">{{ row.market }}</span>
                    <span v-for="tag in row.tags" :key="tag" class="chip tag">{{ tag }}</span>
                  </div>
                </div>
              </td>
              <td class="mono-data">
                {{ row.quote ? formatCurrency(row.quote.price) : '--' }}
              </td>
              <td class="mono-data">
                {{ row.quote?.market_cap ? formatMarketCap(row.quote.market_cap) : '--' }}
              </td>
              <td class="mono-data">
                {{ row.quote ? formatMarketVolume(row.quote.volume) : '--' }}
              </td>
              <td :class="['font-semibold', marketToneClass(normalizeDailyChangePercent(row.quote?.change_percent ?? 0))]">
                <div v-if="row.quote">
                  <div class="mono-data">{{ formatDailyChangeAmount(row.quote) }}</div>
                  <div class="mono-data mt-1 text-xs opacity-80">{{ formatMarketChange(row.quote.change_percent) }}</div>
                </div>
                <template v-else>--</template>
              </td>
              <td :class="['mono-data font-semibold', marketToneClass(row.quote?.ytd_change_percent ?? 0)]">
                {{ row.quote?.ytd_change_percent !== null && row.quote?.ytd_change_percent !== undefined ? formatMarketChange(row.quote.ytd_change_percent) : '--' }}
              </td>
              <td>
                <div class="note-cell">
                  <input
                    :value="noteDrafts[row.id] ?? ''"
                    class="field-input note-input"
                    type="text"
                    maxlength="255"
                    placeholder="输入备注"
                    @input="updateNoteDraft(row.id, $event)"
                    @blur="saveNote(row)"
                  />

                  <el-popover
                    placement="left-start"
                    :width="280"
                    trigger="click"
                    :teleported="false"
                    popper-class="watchlist-action-popover"
                  >
                    <template #reference>
                      <button class="secondary-button !min-h-10 px-3" type="button">操作</button>
                    </template>

                    <div class="menu-panel">
                      <button class="menu-action" type="button" @click="togglePinned(row)">
                        {{ row.is_pinned ? '取消钉住' : '钉住置顶' }}
                      </button>
                      <button class="menu-action" type="button" @click="moveItemBoundary(row, 'top')">
                        置顶
                      </button>
                      <button class="menu-action" type="button" @click="moveItemBoundary(row, 'bottom')">
                        置底
                      </button>
                      <button class="menu-action" type="button" @click="sortMode = true">
                        编辑排序
                      </button>
                      <button class="menu-action" type="button" @click="toggleSpecialAttention(row)">
                        {{ row.is_special_attention ? '取消特别关注' : '特别关注' }}
                      </button>
                      <button class="menu-action" type="button" @click="openAiAnalysis(row)">
                        AI分析
                      </button>
                      <button class="menu-action" type="button" @click="openStockDetail(row)">
                        个股详情
                      </button>
                      <div class="menu-field">
                        <label class="field-label !mb-2">修改分组</label>
                        <select v-model="moveGroupTargets[row.id]" class="field-select !min-h-10">
                          <option v-for="group in groups" :key="group.id" :value="group.id">
                            {{ group.name }}
                          </option>
                        </select>
                        <button class="secondary-button mt-2 w-full" type="button" @click="moveItemToGroup(row)">
                          移动到分组
                        </button>
                      </div>
                      <button class="danger-button w-full" type="button" @click="removeSymbol(row.id)">
                        删除自选
                      </button>
                    </div>
                  </el-popover>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <el-drawer v-model="searchOpen" title="全市场检索" direction="rtl" size="420px">
      <div class="space-y-4">
        <div>
          <label class="field-label" for="security-search">代码 / 名称 / 拼音缩写</label>
          <input
            id="security-search"
            v-model.trim="searchQuery"
            class="field-input"
            type="text"
            placeholder="例如 600519 / 茅台 / ndsd"
          />
        </div>

        <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4 text-sm text-[var(--text-secondary)]">
          一期按 A 股优先搜索，支持代码前缀、中文名称和拼音缩写匹配。
        </div>

        <div v-if="searchLoading" class="empty-state !min-h-[180px]">
          <div>搜索中...</div>
        </div>
        <div v-else-if="searchQuery && searchResults.length === 0" class="empty-state !min-h-[180px]">
          <div>没有匹配结果</div>
        </div>
        <div v-else class="space-y-3">
          <div
            v-for="result in searchResults"
            :key="result.symbol"
            class="search-card"
          >
            <div>
              <div class="font-semibold">{{ result.name }}</div>
              <div class="mt-1 flex items-center gap-2 text-sm text-[var(--text-secondary)]">
                <span class="mono-data">{{ result.code }}</span>
                <span class="chip market">{{ result.market }}</span>
                <span v-for="tag in result.tags" :key="tag" class="chip tag">{{ tag }}</span>
              </div>
            </div>
            <button class="add-button" type="button" @click="addSearchResult(result.symbol)">+</button>
          </div>
        </div>
      </div>
    </el-drawer>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { searchSecurities, type SecuritySearchResult } from '../api/securities'
import {
  createWatchlistGroup,
  deleteWatchlistGroup,
  fetchWatchlistGroups,
  reorderWatchlistGroups,
  updateWatchlistGroup,
} from '../api/watchlistGroups'
import { fetchQuotes, type QuoteItem } from '../api/quotes'
import { openQuoteStream, type QuoteStreamMessage } from '../api/quoteStream'
import {
  createWatchlist,
  deleteWatchlist,
  fetchWatchlists,
  reorderWatchlists,
  updateWatchlist,
} from '../api/watchlists'
import ErrorAlert from '../components/ErrorAlert.vue'
import type { WatchlistGroup, WatchlistItem } from '../types/watchlist'
import { formatCurrency } from '../utils/format'
import { isTradingTime } from '../utils/tradingCalendar'

type WatchlistRow = WatchlistItem & {
  quote?: QuoteItem
}

const marketIndexes = [
  { symbol: 'sh000001', label: '上证指数' },
  { symbol: 'sz399001', label: '深证成指' },
  { symbol: 'sz399006', label: '创业板指' },
  { symbol: 'sh000688', label: '科创50' },
  { symbol: 'sh000300', label: '沪深300' },
  { symbol: 'sh000905', label: '中证500' },
]
const router = useRouter()

const loading = ref(false)
const error = ref('')
const groups = ref<WatchlistGroup[]>([])
const items = ref<WatchlistItem[]>([])
const selectedGroupId = ref<number | null>(null)
const quotes = ref<Record<string, QuoteItem>>({})
const indexQuotes = ref<Record<string, QuoteItem>>({})
const noteDrafts = ref<Record<number, string>>({})
const moveGroupTargets = ref<Record<number, number>>({})

const searchOpen = ref(false)
const searchQuery = ref('')
const searchLoading = ref(false)
const searchResults = ref<SecuritySearchResult[]>([])
const sortMode = ref(false)
const draggingItemId = ref<number | null>(null)
const draggingPinned = ref<boolean | null>(null)
const streamConnected = ref(false)

let quoteTimer: ReturnType<typeof setInterval> | null = null
let searchTimer: ReturnType<typeof setTimeout> | null = null
let quoteSocket: WebSocket | null = null
let quoteReconnectTimer: ReturnType<typeof setTimeout> | null = null
let quoteStreamStopping = false

const currentGroup = computed(() => groups.value.find((group) => group.id === selectedGroupId.value) ?? null)
const currentGroupIndex = computed(() => groups.value.findIndex((group) => group.id === selectedGroupId.value))

const hasGroups = computed(() => groups.value.length > 0)
const canDeleteGroup = computed(() => !!currentGroup.value)
const canMoveGroupLeft = computed(() => currentGroupIndex.value > 0)
const canMoveGroupRight = computed(() => currentGroupIndex.value > -1 && currentGroupIndex.value < groups.value.length - 1)

const rows = computed<WatchlistRow[]>(() =>
  items.value.map((item) => ({
    ...item,
    quote: quotes.value[item.symbol],
  })),
)

function marketToneClass(value: number): string {
  if (value > 0) {
    return 'watchlist-up'
  }
  if (value < 0) {
    return 'watchlist-down'
  }
  return 'muted-text'
}

function formatMarketChange(value: number): string {
  const normalized = normalizeDailyChangePercent(value)
  return `${normalized >= 0 ? '+' : ''}${normalized.toFixed(2)}%`
}

function formatDailyChangeAmount(quote: QuoteItem): string {
  const normalizedPercent = normalizeDailyChangePercent(quote.change_percent)
  const ratio = 1 + normalizedPercent / 100
  if (!Number.isFinite(quote.price) || !Number.isFinite(normalizedPercent) || ratio <= 0) {
    return '--'
  }

  const previousClose = quote.price / ratio
  const changeAmount = quote.price - previousClose

  if (Math.abs(changeAmount) < 0.005) {
    return formatCurrency(0)
  }

  return `${changeAmount > 0 ? '+' : '-'}${formatCurrency(Math.abs(changeAmount))}`
}

function normalizeDailyChangePercent(value: number): number {
  return Math.abs(value) > 100 ? value / 100 : value
}

function formatIndexValue(value: number): string {
  return value.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function formatMarketCap(value: number): string {
  if (value >= 1e8) {
    return `${(value / 1e8).toFixed(value >= 1e11 ? 0 : 2)}亿`
  }
  return new Intl.NumberFormat('zh-CN', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)
}

function formatMarketVolume(value: number): string {
  return new Intl.NumberFormat('zh-CN', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)
}

function updateNoteDraft(itemId: number, event: Event): void {
  const target = event.target as HTMLInputElement
  noteDrafts.value[itemId] = target.value
}

async function loadGroups(keepSelection = true): Promise<void> {
  const payload = await fetchWatchlistGroups()
  groups.value = payload

  if (!payload.length) {
    selectedGroupId.value = null
    return
  }

  if (!keepSelection || !selectedGroupId.value || !payload.some((group) => group.id === selectedGroupId.value)) {
    selectedGroupId.value = payload[0].id
  }
}

async function loadItems(): Promise<void> {
  items.value = await fetchWatchlists(selectedGroupId.value)
  noteDrafts.value = Object.fromEntries(items.value.map((item) => [item.id, item.note ?? '']))
  moveGroupTargets.value = Object.fromEntries(items.value.map((item) => [item.id, item.group_id ?? selectedGroupId.value ?? 0]))
}

async function refreshQuotes(): Promise<void> {
  if (items.value.length === 0) {
    quotes.value = {}
  } else {
    const quoteItems = await fetchQuotes(items.value.map((item) => item.symbol))
    quotes.value = Object.fromEntries(quoteItems.map((quote) => [quote.symbol, quote]))
  }
  const indexQuoteItems = await fetchQuotes(marketIndexes.map((item) => item.symbol))
  indexQuotes.value = Object.fromEntries(indexQuoteItems.map((quote) => [quote.symbol, quote]))
}

function quoteStreamSymbols(): string[] {
  return [...new Set([...items.value.map((item) => item.symbol), ...marketIndexes.map((item) => item.symbol)])]
}

function applyQuoteStreamMessage(message: QuoteStreamMessage): void {
  if (message.type !== 'quotes' || !message.quotes) {
    return
  }
  const watchlistSymbols = new Set(items.value.map((item) => item.symbol))
  const indexSymbols = new Set(marketIndexes.map((item) => item.symbol))
  quotes.value = {
    ...quotes.value,
    ...Object.fromEntries(message.quotes.filter((quote) => watchlistSymbols.has(quote.symbol)).map((quote) => [quote.symbol, quote])),
  }
  indexQuotes.value = {
    ...indexQuotes.value,
    ...Object.fromEntries(message.quotes.filter((quote) => indexSymbols.has(quote.symbol)).map((quote) => [quote.symbol, quote])),
  }
}

async function refreshAll(): Promise<void> {
  loading.value = true
  error.value = ''

  try {
    await loadGroups(true)
    await loadItems()
    await refreshQuotes()
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : '自选股数据加载失败'
  } finally {
    loading.value = false
  }
}

async function refreshQuotesSilently(): Promise<void> {
  if (loading.value || !isTradingTime()) {
    return
  }

  try {
    await refreshQuotes()
  } catch {
    // Keep previous snapshots on transient polling failures.
  }
}

function startPolling(): void {
  stopPolling()
  if (!isTradingTime()) {
    return
  }
  startQuoteStream()
  quoteTimer = setInterval(() => {
    void refreshQuotesSilently()
  }, 5000)
}

function startQuoteStream(): void {
  stopQuoteStream()
  const symbols = quoteStreamSymbols()
  if (!symbols.length) {
    return
  }
  quoteStreamStopping = false
  quoteSocket = openQuoteStream(symbols, applyQuoteStreamMessage, 5)
  quoteSocket.addEventListener('open', () => {
    streamConnected.value = true
  })
  quoteSocket.addEventListener('close', () => {
    streamConnected.value = false
    if (!quoteStreamStopping) {
      scheduleQuoteStreamReconnect()
    }
  })
  quoteSocket.addEventListener('error', () => {
    streamConnected.value = false
  })
}

function scheduleQuoteStreamReconnect(): void {
  if (quoteReconnectTimer || !isTradingTime()) {
    return
  }
  quoteReconnectTimer = setTimeout(() => {
    quoteReconnectTimer = null
    startQuoteStream()
  }, 3000)
}

function stopQuoteStream(): void {
  quoteStreamStopping = true
  if (quoteReconnectTimer) {
    clearTimeout(quoteReconnectTimer)
    quoteReconnectTimer = null
  }
  if (quoteSocket) {
    quoteSocket.close()
    quoteSocket = null
  }
  streamConnected.value = false
}

function stopPolling(): void {
  stopQuoteStream()
  if (quoteTimer) {
    clearInterval(quoteTimer)
    quoteTimer = null
  }
  if (searchTimer) {
    clearTimeout(searchTimer)
    searchTimer = null
  }
}

function selectGroup(groupId: number): void {
  selectedGroupId.value = groupId
}

function toggleSortMode(): void {
  sortMode.value = !sortMode.value
  draggingItemId.value = null
  draggingPinned.value = null
}

async function createGroup(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入分组名称', '新建分组', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputPlaceholder: '例如 白酒 / 医药 / 观察股2',
      inputValidator: (input: string) => (input.trim() ? true : '分组名称不能为空'),
    })
    await createWatchlistGroup({ name: value })
    await loadGroups(false)
    ElMessage.success('分组已创建')
  } catch {
    // user cancelled
  }
}

async function renameGroup(): Promise<void> {
  if (!currentGroup.value) {
    return
  }
  if (currentGroup.value.is_system) {
    ElMessage.warning('系统默认分组不支持重命名')
    return
  }

  try {
    const { value } = await ElMessageBox.prompt('请输入新的分组名称', '重命名分组', {
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValue: currentGroup.value.name,
      inputValidator: (input: string) => (input.trim() ? true : '分组名称不能为空'),
    })
    await updateWatchlistGroup(currentGroup.value.id, { name: value })
    await loadGroups(true)
    ElMessage.success('分组名称已更新')
  } catch {
    // user cancelled
  }
}

async function moveGroup(direction: 'left' | 'right'): Promise<void> {
  if (!currentGroup.value) {
    return
  }

  const next = [...groups.value]
  const index = next.findIndex((group) => group.id === currentGroup.value?.id)
  const targetIndex = direction === 'left' ? index - 1 : index + 1
  if (index < 0 || targetIndex < 0 || targetIndex >= next.length) {
    return
  }

  const [group] = next.splice(index, 1)
  next.splice(targetIndex, 0, group)

  await reorderWatchlistGroups({ group_ids: next.map((item) => item.id) })
  groups.value = next
}

async function deleteGroup(): Promise<void> {
  if (!currentGroup.value) {
    return
  }

  try {
    await ElMessageBox.confirm(
      `删除分组“${currentGroup.value.name}”后，分组内个股会被移动到其他分组；如果这是最后一个分组，则会保留为未分组自选。`,
      '删除分组',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
    await deleteWatchlistGroup(currentGroup.value.id)
    await refreshAll()
    ElMessage.success('分组已删除')
  } catch {
    // user cancelled
  }
}

async function addSearchResult(symbol: string): Promise<void> {
  if (!selectedGroupId.value) {
    return
  }

  try {
    await createWatchlist({ symbol, group_id: selectedGroupId.value })
    await refreshAll()
    ElMessage.success('已加入当前分组')
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : '添加自选失败'
  }
}

async function saveNote(row: WatchlistRow): Promise<void> {
  const draft = (noteDrafts.value[row.id] ?? '').trim()
  const previous = row.note ?? ''
  if (draft === previous) {
    return
  }

  try {
    await updateWatchlist(row.id, { note: draft || null })
    await loadItems()
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : '保存备注失败'
  }
}

async function togglePinned(row: WatchlistRow): Promise<void> {
  try {
    await updateWatchlist(row.id, { is_pinned: !row.is_pinned })
    await refreshAll()
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : '更新置顶状态失败'
  }
}

async function toggleSpecialAttention(row: WatchlistRow): Promise<void> {
  try {
    await updateWatchlist(row.id, { is_special_attention: !row.is_special_attention })
    await loadItems()
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : '更新特别关注失败'
  }
}

async function moveItemToGroup(row: WatchlistRow): Promise<void> {
  const targetGroupId = moveGroupTargets.value[row.id]
  if (!targetGroupId || targetGroupId === row.group_id) {
    return
  }

  try {
    await updateWatchlist(row.id, { group_id: targetGroupId, is_pinned: false })
    await refreshAll()
    ElMessage.success('已移动到目标分组')
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : '修改分组失败'
  }
}

async function removeSymbol(itemId: number): Promise<void> {
  try {
    await deleteWatchlist(itemId)
    await refreshAll()
    ElMessage.success('已从自选中移除')
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : '删除自选失败'
  }
}

function openAiAnalysis(row: WatchlistRow): void {
  void router.push({
    name: 'ai',
    query: {
      symbol: row.symbol,
    },
  })
}

function openStockDetail(row: WatchlistRow): void {
  void router.push({
    name: 'stock-detail',
    params: {
      symbol: row.symbol,
    },
  })
}

async function persistOrdering(pinnedIds: number[], regularIds: number[]): Promise<void> {
  if (!selectedGroupId.value) {
    return
  }

  await reorderWatchlists({
    group_id: selectedGroupId.value,
    pinned_ids: pinnedIds,
    regular_ids: regularIds,
  })
  await loadItems()
}

async function moveItemBoundary(row: WatchlistRow, boundary: 'top' | 'bottom'): Promise<void> {
  const pinnedRows = rows.value.filter((item) => item.is_pinned)
  const regularRows = rows.value.filter((item) => !item.is_pinned)
  const targetZone = row.is_pinned ? pinnedRows : regularRows
  const rest = targetZone.filter((item) => item.id !== row.id)
  const ordered = boundary === 'top' ? [row, ...rest] : [...rest, row]

  const pinnedIds = row.is_pinned ? ordered.map((item) => item.id) : pinnedRows.map((item) => item.id)
  const regularIds = row.is_pinned ? regularRows.map((item) => item.id) : ordered.map((item) => item.id)

  try {
    await persistOrdering(pinnedIds, regularIds)
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : '更新排序失败'
  }
}

function onDragStart(row: WatchlistRow): void {
  if (!sortMode.value) {
    return
  }
  draggingItemId.value = row.id
  draggingPinned.value = row.is_pinned
}

function onDragOver(row: WatchlistRow): void {
  if (!sortMode.value) {
    return
  }
  if (draggingPinned.value !== row.is_pinned) {
    return
  }
}

async function onDrop(targetRow: WatchlistRow): Promise<void> {
  if (!sortMode.value || draggingItemId.value === null || draggingItemId.value === targetRow.id) {
    return
  }
  if (draggingPinned.value !== targetRow.is_pinned) {
    return
  }

  const zoneRows = rows.value.filter((item) => item.is_pinned === targetRow.is_pinned)
  const sourceIndex = zoneRows.findIndex((item) => item.id === draggingItemId.value)
  const targetIndex = zoneRows.findIndex((item) => item.id === targetRow.id)
  if (sourceIndex < 0 || targetIndex < 0) {
    return
  }

  const reordered = [...zoneRows]
  const [dragged] = reordered.splice(sourceIndex, 1)
  reordered.splice(targetIndex, 0, dragged)

  const pinnedIds = targetRow.is_pinned
    ? reordered.map((item) => item.id)
    : rows.value.filter((item) => item.is_pinned).map((item) => item.id)
  const regularIds = targetRow.is_pinned
    ? rows.value.filter((item) => !item.is_pinned).map((item) => item.id)
    : reordered.map((item) => item.id)

  try {
    await persistOrdering(pinnedIds, regularIds)
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : '拖拽排序失败'
  } finally {
    draggingItemId.value = null
    draggingPinned.value = null
  }
}

async function runSearch(query: string): Promise<void> {
  const normalized = query.trim()
  if (!normalized) {
    searchResults.value = []
    return
  }

  searchLoading.value = true
  try {
    searchResults.value = await searchSecurities(normalized)
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : '证券搜索失败'
  } finally {
    searchLoading.value = false
  }
}

watch(searchQuery, (value) => {
  if (searchTimer) {
    clearTimeout(searchTimer)
  }
  searchTimer = setTimeout(() => {
    void runSearch(value)
  }, 250)
})

watch(selectedGroupId, () => {
  void refreshAll()
})

onMounted(() => {
  void refreshAll()
  startPolling()
})

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<style scoped>
.watchlist-page {
  --market-up: #ff5b6e;
  --market-down: #2fc083;
}

.market-index-board {
  display: grid;
  gap: 1px;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  border: 1px solid rgba(112, 183, 98, 0.35);
  border-radius: 22px;
  overflow: hidden;
  background: rgba(76, 135, 63, 0.22);
  box-shadow: 0 18px 44px rgba(0, 0, 0, 0.26);
}

.market-index-tile {
  min-height: 110px;
  padding: 18px 16px;
  background: linear-gradient(180deg, rgba(63, 128, 58, 0.96), rgba(41, 104, 49, 0.96));
}

.market-index-label {
  color: rgba(235, 255, 236, 0.82);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.market-index-value {
  margin-top: 14px;
  color: #f5fff3;
  font-size: 24px;
  font-weight: 700;
}

.market-index-change {
  margin-top: 10px;
  font-size: 13px;
  font-weight: 700;
}

.watchlist-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px 16px;
}

.toolbar-cluster {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.toolbar-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 34px;
  min-width: 34px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.03);
  color: var(--text-secondary);
  padding: 0 12px;
  font-size: 12px;
  font-weight: 600;
  transition: border-color 160ms ease, background 160ms ease, color 160ms ease;
}

.toolbar-button:hover:not(:disabled) {
  border-color: rgba(103, 183, 255, 0.22);
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-primary);
}

.toolbar-button:disabled {
  cursor: not-allowed;
  opacity: 0.42;
}

.toolbar-button.accent {
  border-color: rgba(255, 91, 110, 0.26);
  background: rgba(255, 91, 110, 0.1);
  color: #ffd7dd;
}

.toolbar-button.danger {
  border-color: rgba(248, 195, 93, 0.22);
  background: rgba(248, 195, 93, 0.08);
  color: #f8c35d;
}

.toolbar-button.icon-button {
  padding: 0;
  font-size: 14px;
}

.group-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.group-tab {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 42px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.03);
  color: var(--text-secondary);
  padding: 0 16px;
  transition: border-color 180ms ease, background 180ms ease, color 180ms ease;
}

.group-tab small {
  color: var(--text-tertiary);
}

.group-tab.active {
  border-color: rgba(255, 91, 110, 0.4);
  background: rgba(255, 91, 110, 0.12);
  color: #ffe8ec;
}

.stock-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.stock-main,
.stock-subline,
.note-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stock-subline {
  flex-wrap: wrap;
}

.chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 20px;
  border-radius: 999px;
  padding: 0 8px;
  font-size: 11px;
  font-weight: 700;
}

.chip.market {
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-secondary);
}

.chip.tag {
  border: 1px solid rgba(255, 91, 110, 0.28);
  background: rgba(255, 91, 110, 0.12);
  color: #ffd9de;
}

.chip.fixed {
  border: 1px solid rgba(255, 195, 93, 0.28);
  background: rgba(255, 195, 93, 0.12);
  color: #ffe8b2;
}

.chip.focus {
  border: 1px solid rgba(103, 183, 255, 0.28);
  background: rgba(103, 183, 255, 0.12);
  color: #cae6ff;
}

.watchlist-up {
  color: var(--market-up);
}

.watchlist-down {
  color: var(--market-down);
}

.note-cell {
  gap: 10px;
}

.note-input {
  min-width: 150px;
  max-width: 220px;
  min-height: 38px;
  font-size: 13px;
}

.menu-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: var(--text-primary);
}

.menu-action {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: flex-start;
  min-height: 38px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.03);
  color: var(--text-primary);
  padding: 0 12px;
}

.menu-action:hover {
  border-color: rgba(103, 183, 255, 0.18);
  background: rgba(103, 183, 255, 0.08);
}

.menu-field {
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.02);
  padding: 12px;
}

.search-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.03);
  padding: 14px 16px;
}

.add-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 999px;
  border: 1px solid rgba(255, 91, 110, 0.36);
  background: rgba(255, 91, 110, 0.12);
  color: var(--market-up);
  font-size: 20px;
  font-weight: 700;
}

.watchlist-table :deep(tbody tr) {
  transition: background 180ms ease, transform 180ms ease;
}

:deep(.watchlist-action-popover.el-popper) {
  border: 1px solid rgba(103, 183, 255, 0.16);
  background: linear-gradient(180deg, rgba(8, 18, 30, 0.98), rgba(12, 24, 40, 0.98));
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.42);
  color: var(--text-primary);
}

:deep(.watchlist-action-popover.el-popper .el-popper__arrow::before) {
  border: 1px solid rgba(103, 183, 255, 0.16);
  background: rgba(10, 20, 34, 0.98);
}

:deep(.watchlist-action-popover .el-popover__title),
:deep(.watchlist-action-popover .field-label),
:deep(.watchlist-action-popover .menu-panel) {
  color: var(--text-primary);
}

:deep(.watchlist-action-popover .secondary-button),
:deep(.watchlist-action-popover .danger-button) {
  color: var(--text-primary);
}

:deep(.watchlist-action-popover .field-select) {
  width: 100%;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(7, 16, 28, 0.96);
  color: var(--text-primary);
}

:deep(.watchlist-action-popover option) {
  background: #0b1623;
  color: var(--text-primary);
}

.row-dragging {
  opacity: 0.5;
}

@media (max-width: 1280px) {
  .market-index-board {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .market-index-board {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .watchlist-toolbar {
    align-items: stretch;
  }

  .toolbar-cluster {
    width: 100%;
  }

  .note-cell {
    flex-direction: column;
    align-items: stretch;
  }

  .note-input {
    min-width: 100%;
    max-width: 100%;
  }
}
</style>
