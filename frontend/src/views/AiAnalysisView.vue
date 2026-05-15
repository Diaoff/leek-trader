<template>
  <section class="ai-page space-y-4">
    <div class="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
      <PageHeader
        title="AI 分析"
        subtitle="接入你自己的 OpenAI 兼容模型，完成单票研判、参数建议与投资助手问答。"
      />
      <div class="token-row">
        <span :class="['status-chip', configReady ? 'positive' : 'negative']">
          {{ configReady ? '模型已连接' : '请先配置模型' }}
        </span>
        <button class="secondary-button" type="button" :disabled="configLoading" @click="loadConfig">
          重新读取配置
        </button>
      </div>
    </div>

    <ErrorAlert :message="error" type="error" />

    <div class="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
      <div class="panel space-y-4">
        <div class="panel-header !mb-0">
          <div>
            <h3 class="panel-title">模型配置</h3>
            <p class="panel-subtitle">支持多个 Provider，仍按 OpenAI 兼容协议调用。</p>
          </div>
        </div>

        <div>
          <label class="field-label" for="ai-provider">Provider</label>
          <select id="ai-provider" v-model="configForm.provider" class="field-input">
            <option v-for="provider in providerOptions" :key="provider.value" :value="provider.value">
              {{ provider.label }}
            </option>
          </select>
          <div class="field-help">
            <span v-for="provider in providerOptions" :key="provider.value" class="mr-2 inline-flex items-center gap-1">
              <strong>{{ provider.label }}</strong><span>·{{ provider.hint }}</span>
            </span>
          </div>
        </div>

        <div>
          <label class="field-label" for="ai-base-url">Base URL</label>
          <input
            id="ai-base-url"
            v-model.trim="configForm.base_url"
            class="field-input"
            type="text"
            placeholder="例如 https://api.openai.com/v1"
          />
        </div>

        <div>
          <label class="field-label" for="ai-api-key">API Key</label>
          <input
            id="ai-api-key"
            v-model.trim="configForm.api_key"
            class="field-input"
            type="password"
            placeholder="输入你的模型密钥"
          />
        </div>

        <div>
          <label class="field-label" for="ai-model">Model</label>
          <input
            id="ai-model"
            v-model.trim="configForm.model"
            class="field-input"
            type="text"
            placeholder="例如 gpt-4o-mini / qwen-plus / deepseek-chat"
          />
        </div>

        <div class="flex flex-wrap gap-3">
          <button class="primary-button" type="button" :disabled="configSaving" @click="saveConfig">
            {{ configSaving ? '保存中...' : '保存配置' }}
          </button>
          <button class="secondary-button" type="button" :disabled="configSaving" @click="resetConfigForm">
            重置
          </button>
        </div>

        <div class="config-tip">
          <div class="config-tip-title">兼容说明</div>
          <p>如果地址已经带有 `/chat/completions`，系统会直接调用；否则会自动拼接该路径。</p>
        </div>
      </div>

      <div class="panel space-y-4">
        <div class="panel-header !mb-0">
          <div>
            <h3 class="panel-title">单票 AI 分析</h3>
            <p class="panel-subtitle">参考交易研究流程，用实时行情和近段时间日线生成研究摘要。</p>
          </div>
          <button class="primary-button" type="button" :disabled="!selectedSecurity || analysisLoading || !configReady" @click="runStockAnalysis">
            {{ analysisLoading ? '分析中...' : '开始分析' }}
          </button>
        </div>

        <div>
          <label class="field-label" for="stock-search">股票检索</label>
          <input
            id="stock-search"
            v-model.trim="searchQuery"
            class="field-input"
            type="text"
            placeholder="输入代码 / 名称 / 拼音缩写"
          />
          <div class="field-help">优先使用当前项目的证券搜索结果。</div>
        </div>

        <div v-if="searchQuery && searchLoading" class="compact-empty">搜索中...</div>
        <div v-else-if="searchResults.length" class="search-result-list">
          <button
            v-for="result in searchResults"
            :key="result.symbol"
            class="search-result-item"
            type="button"
            @click="selectSecurity(result)"
          >
            <div>
              <div class="search-result-name">{{ result.name }}</div>
              <div class="search-result-meta">
                <span class="mono-data">{{ result.code }}</span>
                <span class="chip market">{{ result.market }}</span>
                <span v-for="tag in result.tags" :key="tag" class="chip tag">{{ tag }}</span>
              </div>
            </div>
            <span class="status-chip subtle">选择</span>
          </button>
        </div>

        <div v-if="selectedSecurity" class="selected-stock-card">
          <div>
            <div class="selected-stock-name">{{ selectedSecurity.name }}</div>
            <div class="search-result-meta">
              <span class="mono-data">{{ selectedSecurity.code }}</span>
              <span class="chip market">{{ selectedSecurity.market }}</span>
              <span v-for="tag in selectedSecurity.tags" :key="tag" class="chip tag">{{ tag }}</span>
            </div>
          </div>
          <button class="secondary-button" type="button" @click="clearSelectedSecurity">
            清空
          </button>
        </div>

        <div>
          <label class="field-label" for="analysis-note">分析备注</label>
          <textarea
            id="analysis-note"
            v-model="analysisNote"
            class="field-textarea"
            rows="4"
            placeholder="可选：补充你的持仓逻辑、关注点或交易计划。"
          />
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <div>
          <h3 class="panel-title">分析输出</h3>
          <p class="panel-subtitle">
            {{ stockAnalysis ? `${stockAnalysis.security.name} · ${stockAnalysis.security.code}` : '尚未生成分析结果' }}
          </p>
        </div>
        <div v-if="stockAnalysis" class="token-row">
          <span v-if="stockAnalysis.latest_price !== null" class="status-chip subtle mono-data">
            {{ formatCurrency(stockAnalysis.latest_price) }}
          </span>
          <span
            v-if="stockAnalysis.change_percent !== null"
            :class="['status-chip', stockAnalysis.change_percent >= 0 ? 'rise' : 'fall']"
          >
            {{ formatMarketChange(stockAnalysis.change_percent) }}
          </span>
          <span class="status-chip subtle mono-data">{{ formatTime(stockAnalysis.generated_at) }}</span>
        </div>
      </div>

      <div v-if="analysisLoading && !stockAnalysis" class="empty-state !min-h-[260px]">
        <div>AI 正在整理当前股票的结构与风险。</div>
      </div>
      <div v-else-if="stockAnalysis" class="analysis-output markdown-body">
        <div v-if="analysisLoading" class="streaming-indicator">正在流式生成...</div>
        <div v-html="renderMarkdownContent(stockAnalysis.content)" />
      </div>
      <div v-else class="empty-state !min-h-[260px]">
        <div>选择一只股票后即可生成 AI 分析。</div>
        <div class="text-sm text-[var(--text-tertiary)]">当前会把实时行情和近段时间日线一并发送给你配置的大模型。</div>
      </div>
    </div>

    <div class="panel space-y-4">
      <div class="panel-header !mb-0">
        <div>
          <h3 class="panel-title">参数建议</h3>
          <p class="panel-subtitle">基于当前策略参数、回测/优化结果给出建议，不会自动写回。</p>
        </div>
        <button class="secondary-button" type="button" :disabled="adviceLoading || !selectedSecurity || !configReady" @click="requestParameterAdvice">
          {{ adviceLoading ? '分析中...' : '请求建议' }}
        </button>
      </div>

      <div class="workflow-grid">
        <div class="workflow-step">
          <div class="section-label">Input</div>
          <h4 class="workflow-title">输入区</h4>
          <p class="workflow-copy">从回测/优化报告跳转时会自动带入标的、策略、任务 ID 和合并参数。</p>
        </div>
        <div class="workflow-step">
          <div class="section-label">AI Output</div>
          <h4 class="workflow-title">AI 输出区</h4>
          <p class="workflow-copy">保留结构化 JSON、raw content、warnings 和可恢复失败提示。</p>
        </div>
        <div class="workflow-step">
          <div class="section-label">Confirm</div>
          <h4 class="workflow-title">确认区</h4>
          <p class="workflow-copy">人工确认后再进入策略调整，当前页面不会自动写回参数。</p>
        </div>
      </div>

      <div class="rounded-[20px] border border-white/5 bg-black/10 p-4">
        <div class="section-label">研究上下文摘要</div>
        <div class="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div>
            <div class="text-xs text-[var(--text-tertiary)]">来源类型</div>
            <div class="mt-1 text-sm text-[var(--text-secondary)]">{{ describeAiSuggestionSource(parameterAdviceRouteContext.source) }}</div>
          </div>
          <div>
            <div class="text-xs text-[var(--text-tertiary)]">模板名</div>
            <div class="mt-1 text-sm text-[var(--text-secondary)]">{{ parameterAdviceRouteContext.templateName || '--' }}</div>
          </div>
          <div>
            <div class="text-xs text-[var(--text-tertiary)]">参数来源</div>
            <div class="mt-1 text-sm text-[var(--text-secondary)]">{{ describeAiParameterSource(parameterAdviceRouteContext.parameterSource) }}</div>
          </div>
          <div class="md:col-span-2 xl:col-span-1">
            <div class="text-xs text-[var(--text-tertiary)]">模板参数摘要</div>
            <div class="mt-1 text-sm text-[var(--text-secondary)]">{{ summarizeObject(parameterAdviceRouteContext.templateParameters) }}</div>
          </div>
        </div>
      </div>

      <div class="rounded-[20px] border border-white/5 bg-black/10 p-4">
        <div class="section-label">事件链上下文</div>
        <div v-if="eventChainRouteContext.hasContext" class="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div>
            <div class="text-xs text-[var(--text-tertiary)]">策略运行 ID</div>
            <div class="mt-1 text-sm text-[var(--text-secondary)]">{{ eventChainRouteContext.strategyRunId ?? '--' }}</div>
          </div>
          <div>
            <div class="text-xs text-[var(--text-tertiary)]">订单 ID</div>
            <div class="mt-1 text-sm text-[var(--text-secondary)]">{{ eventChainRouteContext.orderId ?? '--' }}</div>
          </div>
          <div class="md:col-span-2">
            <div class="text-xs text-[var(--text-tertiary)]">Correlation ID</div>
            <div class="mt-1 break-all text-sm text-[var(--text-secondary)]">{{ eventChainRouteContext.correlationId || '--' }}</div>
          </div>
        </div>
        <div v-else class="mt-4 rounded-[16px] border border-amber-300/20 bg-amber-300/[0.06] px-4 py-3 text-sm text-[var(--text-secondary)]">
          {{ eventChainRouteContext.degradedMessage }}
        </div>
      </div>

      <div>
        <label class="field-label" for="strategy-type">策略类型</label>
        <input id="strategy-type" v-model.trim="parameterAdviceForm.strategy_type" class="field-input" type="text" placeholder="moving_average / macd / ..." />
        <p class="field-help mt-2">参数建议固定使用后端 parameter_advisor，不会先运行通用 Agent。</p>
      </div>

      <div>
        <label class="field-label" for="current-parameters">当前参数 / 合并参数</label>
        <textarea id="current-parameters" v-model="parameterAdviceParametersText" class="field-textarea" rows="5" placeholder='{"fast_window": 5, "slow_window": 20}' />
        <p v-if="parameterAdviceHint" class="field-help mt-2 text-amber-100">{{ parameterAdviceHint }}</p>
      </div>

      <div class="grid gap-3 md:grid-cols-2">
        <div>
          <label class="field-label" for="optimization-job-id">优化任务 ID</label>
          <input id="optimization-job-id" v-model.trim="parameterAdviceForm.optimization_job_id" class="field-input" type="text" placeholder="可选" />
        </div>
        <div>
          <label class="field-label" for="backtest-job-id">回测任务 ID</label>
          <input id="backtest-job-id" v-model.trim="parameterAdviceForm.backtest_job_id" class="field-input" type="text" placeholder="可选" />
        </div>
      </div>

      <div v-if="parameterAdvice" class="analysis-output markdown-body">
        <div class="streaming-indicator">{{ parameterAdvice.recoverable ? '可恢复结果' : '参数建议结果' }}</div>
        <div v-html="renderMarkdownContent(parameterAdvice.content)" />
        <pre v-if="parameterAdvice.structured.data" class="mt-4 overflow-auto rounded-2xl bg-black/40 p-4 text-xs text-[var(--text-secondary)]">{{ formatStructuredData(parameterAdvice.structured.data) }}</pre>
        <pre v-if="parameterAdvice.structured.raw_content" class="mt-4 overflow-auto rounded-2xl bg-black/40 p-4 text-xs text-[var(--text-secondary)]">{{ parameterAdvice.structured.raw_content }}</pre>
        <div v-if="parameterAdvice.warnings.length" class="mt-4 space-y-2 text-sm text-[var(--text-secondary)]">
          <div v-for="warning in parameterAdvice.warnings" :key="warning">{{ warning }}</div>
        </div>
        <div class="mt-4 rounded-2xl border border-amber-300/20 bg-amber-300/10 p-4 text-sm text-amber-100">
          样本内参数可能过拟合，请先做样本外验证或小资金观察，再决定是否调整策略。
        </div>
      </div>
      <div v-else class="empty-state !min-h-[180px]">
        <div>填写参数后可请求 AI 给出参数建议。</div>
      </div>

      <div class="confirmation-card">
        <div>
          <div class="section-label">Human Confirmation</div>
          <h4 class="workflow-title">人工确认</h4>
          <p class="workflow-copy">确认仅记录当前页面状态，后续可带着建议去策略页手动调整。</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <button class="secondary-button" type="button" :disabled="!parameterAdvice" @click="rejectParameterAdvice">
            暂不采用
          </button>
          <button class="primary-button" type="button" :disabled="!parameterAdvice || parameterAdvice.recoverable" @click="confirmParameterAdvice">
            确认建议
          </button>
        </div>
        <div v-if="parameterAdviceDecision" class="status-chip positive">{{ parameterAdviceDecision }}</div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <div>
          <h3 class="panel-title">AI 投资助手</h3>
          <p class="panel-subtitle">支持多轮对话，沿用当前页面的模型配置。</p>
        </div>
        <button class="secondary-button" type="button" :disabled="chatLoading || chatMessages.length === 0" @click="clearChat">
          清空会话
        </button>
      </div>

      <div class="chat-shell">
        <div v-if="chatMessages.length === 0" class="empty-state !min-h-[240px]">
          <div>还没有聊天记录。</div>
          <div class="text-sm text-[var(--text-tertiary)]">可以直接问个股、板块、风格轮动或风险控制问题。</div>
        </div>
        <div v-else class="chat-list">
          <div
            v-for="(message, index) in chatMessages"
            :key="`${message.role}-${index}`"
            :class="['chat-message', message.role]"
          >
            <div class="chat-role">{{ message.role === 'user' ? '你' : 'AI' }}</div>
            <div class="chat-content markdown-body" v-html="renderMarkdownContent(message.content)" />
          </div>
        </div>

        <div class="chat-composer">
          <textarea
            v-model="chatInput"
            class="field-textarea chat-textarea"
            rows="4"
            placeholder="输入你想让 AI 分析的问题，按 Enter 发送，Shift + Enter 换行。"
            @keydown.enter.exact.prevent="sendChatMessage"
          />
          <div class="chat-actions">
            <span class="field-help">建议一次只问一个明确问题，输出会更稳定。</span>
            <button class="primary-button" type="button" :disabled="chatLoading || !chatInput.trim() || !configReady" @click="sendChatMessage">
              {{ chatLoading ? '发送中...' : '发送' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'

import {
  fetchAiConfig,
  requestAiParameterAdvice,
  streamAiChat,
  streamAiStockAnalysis,
  updateAiConfig,
  type AiStreamEvent,
} from '../api/ai'
import { searchSecurities, type SecuritySearchResult } from '../api/securities'
import ErrorAlert from '../components/ErrorAlert.vue'
import PageHeader from '../components/PageHeader.vue'
import type { AiChatMessage, AiConfig, AiParameterAdviceResponse, AiStockAnalysis, AiProvider } from '../types/ai'
import {
  describeAiParameterSource,
  describeAiSuggestionSource,
  firstQueryString,
  parseJsonObject,
  summarizeObject,
  type AiParameterSource,
  type AiSuggestionSource,
} from '../utils/aiSuggestionContext'
import { renderMarkdown } from '../utils/markdown'
import { formatCurrency } from '../utils/format'

const route = useRoute()

const providerOptions: Array<{ value: AiProvider; label: string; hint: string }> = [
  { value: 'openai_compatible', label: 'OpenAI 兼容', hint: '通用兼容端点' },
  { value: 'deepseek', label: 'DeepSeek', hint: 'DeepSeek 兼容端点' },
  { value: 'siliconflow', label: 'SiliconFlow', hint: 'SiliconFlow 兼容端点' },
  { value: 'ollama', label: 'Ollama', hint: '本地兼容端点' },
  { value: 'custom', label: '自定义', hint: '手动填写兼容端点' },
]

const error = ref('')
const configLoading = ref(false)
const configSaving = ref(false)
const analysisLoading = ref(false)
const chatLoading = ref(false)
const adviceLoading = ref(false)

const configForm = reactive<AiConfig>({
  provider: 'openai_compatible',
  base_url: '',
  api_key: '',
  model: '',
  configured: false,
})

const searchQuery = ref('')
const searchLoading = ref(false)
const searchResults = ref<SecuritySearchResult[]>([])
const selectedSecurity = ref<SecuritySearchResult | null>(null)
const analysisNote = ref('')
const stockAnalysis = ref<AiStockAnalysis | null>(null)
const parameterAdvice = ref<AiParameterAdviceResponse | null>(null)
const parameterAdviceDecision = ref('')
const defaultParameterAdviceParametersText = '{"fast_window": 5, "slow_window": 20}'
const parameterAdviceParametersText = ref(defaultParameterAdviceParametersText)
const parameterAdviceHint = ref('')
const parameterAdviceForm = reactive({
  strategy_type: 'moving_average',
  optimization_job_id: '',
  backtest_job_id: '',
})

interface ParameterAdviceRouteContext {
  source: AiSuggestionSource | null
  parameterSource: AiParameterSource | null
  templateKey: string
  templateName: string
  templateParameters: Record<string, unknown>
  currentParameters: Record<string, unknown>
}

const parameterAdviceRouteContext = computed<ParameterAdviceRouteContext>(() => readRouteSuggestionContext())
const eventChainRouteContext = computed(() => readEventChainRouteContext())

interface ParsedRouteSuggestionContext extends ParameterAdviceRouteContext {
  symbol: string
  strategyType: string
  optimizationJobId: string
  backtestJobId: string
  templateParametersRaw: string
  currentParametersRaw: string
  parametersMissing: boolean
}

interface EventChainRouteContext {
  strategyRunId: number | null
  orderId: number | null
  correlationId: string
  hasContext: boolean
  degradedMessage: string | null
}

function readRouteSuggestionContext(): ParsedRouteSuggestionContext {
  const symbol = firstQueryString(route.query.symbol)
  const strategyType = firstQueryString(route.query.strategyType)
  const optimizationJobId = firstQueryString(route.query.optimizationJobId)
  const backtestJobId = firstQueryString(route.query.backtestJobId)
  const templateParametersRaw = firstQueryString(route.query.templateParameters)
  const currentParametersRaw = firstQueryString(route.query.currentParameters)
  const parameterSourceRaw = firstQueryString(route.query.parameterSource)
  const sourceRaw = firstQueryString(route.query.source)
  const parametersMissing = firstQueryString(route.query.parametersMissing) === '1'

  return {
    source: isSuggestionSource(sourceRaw) ? sourceRaw : null,
    parameterSource: isParameterSource(parameterSourceRaw) ? parameterSourceRaw : null,
    templateKey: firstQueryString(route.query.templateKey),
    templateName: firstQueryString(route.query.templateName),
    templateParameters: parseJsonObject(templateParametersRaw),
    currentParameters: parseJsonObject(currentParametersRaw),
    symbol,
    strategyType,
    optimizationJobId,
    backtestJobId,
    templateParametersRaw,
    currentParametersRaw,
    parametersMissing,
  }
}

function readEventChainRouteContext(): EventChainRouteContext {
  const strategyRunId = firstNumericRouteValue(route.query.strategyRunId)
  const orderId = firstNumericRouteValue(route.query.orderId)
  const correlationId = firstStringRouteValue(route.query.correlationId)
  const hasContext = strategyRunId !== null || orderId !== null || Boolean(correlationId)
  return {
    strategyRunId,
    orderId,
    correlationId,
    hasContext,
    degradedMessage: hasContext ? null : '未携带事件链，将仅使用当前标的/参数上下文。',
  }
}

function isSuggestionSource(value: string): value is AiSuggestionSource {
  return value === 'strategy-template' || value === 'backtest-result' || value === 'optimization-result'
}

function isParameterSource(value: string): value is AiParameterSource {
  return value === 'template' || value === 'example' || value === 'empty'
}

function applyRouteSuggestionContext(): void {
  parameterAdvice.value = null
  parameterAdviceDecision.value = ''
  parameterAdviceHint.value = ''
  parameterAdviceForm.strategy_type = 'moving_average'
  parameterAdviceForm.optimization_job_id = ''
  parameterAdviceForm.backtest_job_id = ''
  parameterAdviceParametersText.value = defaultParameterAdviceParametersText

  const context = readRouteSuggestionContext()
  if (context.symbol) {
    searchQuery.value = context.symbol
  }
  if (context.strategyType) {
    parameterAdviceForm.strategy_type = context.strategyType
  }
  if (context.optimizationJobId) {
    parameterAdviceForm.optimization_job_id = context.optimizationJobId
  }
  if (context.backtestJobId) {
    parameterAdviceForm.backtest_job_id = context.backtestJobId
  }
  if (context.templateParametersRaw.trim()) {
    parameterAdviceParametersText.value = context.templateParametersRaw
  } else if (context.currentParametersRaw.trim()) {
    parameterAdviceParametersText.value = context.currentParametersRaw
  }
  if (context.parameterSource === 'empty' || context.parametersMissing) {
    parameterAdviceHint.value = '未找到运行参数，请人工确认当前参数。'
  }
}

const chatMessages = ref<AiChatMessage[]>([])
const chatInput = ref('')

let searchTimer: ReturnType<typeof setTimeout> | null = null
let routeSymbolHandled = ''
let skipNextSearch = false
let searchRequestId = 0
let analysisAbortController: AbortController | null = null
let chatAbortController: AbortController | null = null

const configReady = computed(() => {
  const keyReady = configForm.provider === 'ollama' || Boolean(configForm.api_key.trim())
  return Boolean(configForm.base_url.trim() && configForm.model.trim() && keyReady)
})

function resetConfigForm(): void {
  configForm.provider = 'openai_compatible'
  configForm.base_url = ''
  configForm.api_key = ''
  configForm.model = ''
  configForm.configured = false
}

async function loadConfig(): Promise<void> {
  configLoading.value = true
  error.value = ''
  try {
    const payload = await fetchAiConfig()
    configForm.provider = payload.provider
    configForm.base_url = payload.base_url
    configForm.api_key = payload.api_key
    configForm.model = payload.model
    configForm.configured = payload.configured
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : '读取 AI 配置失败'
  } finally {
    configLoading.value = false
  }
}

async function saveConfig(): Promise<void> {
  configSaving.value = true
  error.value = ''
  try {
    const payload = await updateAiConfig({
      provider: configForm.provider,
      base_url: configForm.base_url,
      api_key: configForm.api_key,
      model: configForm.model,
    })
    configForm.configured = payload.configured
    ElMessage.success('AI 配置已保存')
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : '保存 AI 配置失败'
  } finally {
    configSaving.value = false
  }
}

function selectSecurity(security: SecuritySearchResult): void {
  skipNextSearch = true
  selectedSecurity.value = security
  searchQuery.value = `${security.name} ${security.code}`
  searchResults.value = []
}

function clearSelectedSecurity(): void {
  selectedSecurity.value = null
  stockAnalysis.value = null
}

function renderMarkdownContent(value: string): string {
  return renderMarkdown(value)
}

function formatStructuredData(value: Record<string, unknown>): string {
  return JSON.stringify(value, null, 2)
}

function formatMarketChange(value: number): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function formatTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

async function runSearch(query: string): Promise<void> {
  const normalized = query.trim()
  const requestId = ++searchRequestId

  if (!normalized) {
    searchResults.value = []
    searchLoading.value = false
    return
  }

  searchLoading.value = true
  try {
    const results = await searchSecurities(normalized)
    if (requestId === searchRequestId && normalized === searchQuery.value.trim()) {
      searchResults.value = results
    }
  } catch (err: unknown) {
    if (requestId === searchRequestId) {
      error.value = err instanceof Error ? err.message : '证券搜索失败'
      searchResults.value = []
    }
  } finally {
    if (requestId === searchRequestId) {
      searchLoading.value = false
    }
  }
}

async function hydrateFromRouteSymbol(symbol: string): Promise<void> {
  const normalized = symbol.trim().toLowerCase()
  if (!normalized || normalized === routeSymbolHandled) {
    return
  }

  searchLoading.value = true
  error.value = ''
  try {
    const results = await searchSecurities(normalized)
    const matched =
      results.find((item) => item.symbol.toLowerCase() === normalized) ??
      results.find((item) => item.code.toLowerCase() === normalized.replace(/^(sh|sz|bj)/, ''))

    if (!matched) {
      return
    }

    routeSymbolHandled = normalized
    selectedSecurity.value = matched
    searchQuery.value = `${matched.name} ${matched.code}`

    if (configReady.value) {
      await runStockAnalysis()
    }
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : '读取路由股票参数失败'
  } finally {
    searchLoading.value = false
  }
}

async function runStockAnalysis(): Promise<void> {
  if (!selectedSecurity.value) {
    ElMessage.warning('请先选择股票')
    return
  }
  if (!configReady.value) {
    ElMessage.warning('请先完成 AI 模型配置')
    return
  }

  analysisLoading.value = true
  error.value = ''
  analysisAbortController?.abort()
  analysisAbortController = new AbortController()

  stockAnalysis.value = {
    symbol: selectedSecurity.value.symbol,
    security: {
      symbol: selectedSecurity.value.symbol,
      code: selectedSecurity.value.code,
      name: selectedSecurity.value.name,
      market: selectedSecurity.value.market,
      tags: selectedSecurity.value.tags,
    },
    content: '',
    generated_at: new Date().toISOString(),
    latest_price: null,
    change_percent: null,
  }

  try {
    await streamAiStockAnalysis(
      selectedSecurity.value.symbol,
      analysisNote.value,
      handleAnalysisStreamEvent,
      analysisAbortController.signal,
    )
  } catch (err: unknown) {
    if (!isAbortError(err)) {
      error.value = err instanceof Error ? err.message : 'AI 股票分析失败'
    }
  } finally {
    analysisLoading.value = false
    analysisAbortController = null
  }
}

async function sendChatMessage(): Promise<void> {
  const message = chatInput.value.trim()
  if (!message) {
    return
  }
  if (!configReady.value) {
    ElMessage.warning('请先完成 AI 模型配置')
    return
  }

  const nextMessages = [...chatMessages.value, { role: 'user', content: message } as AiChatMessage]
  chatMessages.value = [...nextMessages, { role: 'assistant', content: '' }]
  chatInput.value = ''
  chatLoading.value = true
  error.value = ''
  chatAbortController?.abort()
  chatAbortController = new AbortController()

  try {
    await streamAiChat(nextMessages, handleChatStreamEvent, chatAbortController.signal)
  } catch (err: unknown) {
    if (!isAbortError(err)) {
      error.value = err instanceof Error ? err.message : 'AI 对话失败'
    }
  } finally {
    chatLoading.value = false
    chatAbortController = null
  }
}

function clearChat(): void {
  chatAbortController?.abort()
  chatMessages.value = []
}

async function requestParameterAdvice(): Promise<void> {
  if (!selectedSecurity.value) {
    ElMessage.warning('请先选择股票')
    return
  }
  if (!configReady.value) {
    ElMessage.warning('请先完成 AI 模型配置')
    return
  }

  adviceLoading.value = true
  error.value = ''
  parameterAdviceDecision.value = ''
  try {
    const currentParameters = parameterAdviceParametersText.value.trim()
      ? JSON.parse(parameterAdviceParametersText.value)
      : {}
    parameterAdvice.value = await requestAiParameterAdvice({
      symbol: selectedSecurity.value.symbol,
      strategy_type: parameterAdviceForm.strategy_type.trim() || 'moving_average',
      current_parameters: currentParameters,
      optimization_job_id: parameterAdviceForm.optimization_job_id.trim() || undefined,
      backtest_job_id: parameterAdviceForm.backtest_job_id.trim() || undefined,
      strategy_run_id: firstNumericRouteValue(route.query.strategyRunId),
      order_id: firstNumericRouteValue(route.query.orderId),
      correlation_id: firstStringRouteValue(route.query.correlationId) || undefined,
    })
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'AI 参数建议失败'
  } finally {
    adviceLoading.value = false
  }
}

function confirmParameterAdvice(): void {
  if (!parameterAdvice.value || parameterAdvice.value.recoverable) {
    return
  }
  parameterAdviceDecision.value = '已确认，下一步请前往策略中心手动调整参数。'
  ElMessage.success('参数建议已确认')
}

function rejectParameterAdvice(): void {
  if (!parameterAdvice.value) {
    return
  }
  parameterAdviceDecision.value = '已标记为暂不采用。'
  ElMessage.info('已暂不采用本次建议')
}

function handleAnalysisStreamEvent(event: AiStreamEvent): void {
  if (event.type === 'meta') {
    const security = event.payload.security as AiStockAnalysis['security'] | undefined
    stockAnalysis.value = {
      symbol: String(event.payload.symbol ?? stockAnalysis.value?.symbol ?? ''),
      security: security ?? stockAnalysis.value?.security ?? {
        symbol: selectedSecurity.value?.symbol ?? '',
        code: selectedSecurity.value?.code ?? '',
        name: selectedSecurity.value?.name ?? '',
        market: selectedSecurity.value?.market ?? '',
        tags: selectedSecurity.value?.tags ?? [],
      },
      content: stockAnalysis.value?.content ?? '',
      generated_at: String(event.payload.generated_at ?? new Date().toISOString()),
      latest_price: toNullableNumber(event.payload.latest_price),
      change_percent: toNullableNumber(event.payload.change_percent),
    }
    return
  }

  if (event.type === 'chunk') {
    if (!stockAnalysis.value) {
      return
    }
    stockAnalysis.value = {
      ...stockAnalysis.value,
      content: stockAnalysis.value.content + event.content,
    }
    return
  }

  if (event.type === 'error') {
    throw new Error(formatStreamErrorDetail(event.detail))
  }
}

function handleChatStreamEvent(event: AiStreamEvent): void {
  if (event.type === 'chunk') {
    const lastMessage = chatMessages.value.at(-1)
    if (lastMessage && lastMessage.role === 'assistant') {
      lastMessage.content += event.content
    }
    return
  }
  if (event.type === 'error') {
    throw new Error(formatStreamErrorDetail(event.detail))
  }
}

function formatStreamErrorDetail(detail: string | Record<string, unknown>): string {
  if (typeof detail === 'string') {
    return detail
  }
  if (detail && typeof detail === 'object') {
    const row = detail as { message?: unknown; code?: unknown }
    if (typeof row.message === 'string' && row.message.trim()) {
      return row.message
    }
    if (typeof row.code === 'string' && row.code.trim()) {
      return row.code
    }
  }
  return '流式请求失败'
}

function toNullableNumber(value: unknown): number | null {
  return typeof value === 'number' ? value : null
}

function firstStringRouteValue(value: unknown): string {
  if (Array.isArray(value)) {
    return typeof value[0] === 'string' ? value[0] : ''
  }
  return typeof value === 'string' ? value : ''
}

function firstNumericRouteValue(value: unknown): number | null {
  const raw = firstStringRouteValue(value)
  if (!raw) {
    return null
  }
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : null
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

watch(searchQuery, (value) => {
  if (skipNextSearch) {
    skipNextSearch = false
    return
  }
  if (searchTimer) {
    clearTimeout(searchTimer)
  }
  searchTimer = setTimeout(() => {
    void runSearch(value)
  }, 250)
})

watch(
  () => route.query.symbol,
  (symbol) => {
    if (typeof symbol === 'string') {
      void hydrateFromRouteSymbol(symbol)
    }
  },
  { immediate: true },
)

watch(
  () => route.query,
  () => {
    applyRouteSuggestionContext()
  },
  { immediate: true, deep: true },
)

onMounted(() => {
  void (async () => {
    await loadConfig()
    if (typeof route.query.symbol === 'string') {
      if (selectedSecurity.value && configReady.value && !stockAnalysis.value) {
        await runStockAnalysis()
      } else {
        await hydrateFromRouteSymbol(route.query.symbol)
      }
    }
  })()
})

onBeforeUnmount(() => {
  if (searchTimer) {
    clearTimeout(searchTimer)
    searchTimer = null
  }
  analysisAbortController?.abort()
  chatAbortController?.abort()
})
</script>

<style scoped>
.ai-page {
  --market-up: #ff5b6e;
  --market-down: #2fc083;
}

.config-tip {
  border: 1px solid rgba(103, 183, 255, 0.14);
  border-radius: 18px;
  background: rgba(103, 183, 255, 0.08);
  padding: 14px 16px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.config-tip-title {
  margin-bottom: 6px;
  color: var(--text-primary);
  font-weight: 600;
}

.compact-empty {
  display: flex;
  min-height: 88px;
  align-items: center;
  justify-content: center;
  border-radius: 18px;
  border: 1px dashed rgba(255, 255, 255, 0.08);
  color: var(--text-secondary);
}

.search-result-list {
  display: flex;
  max-height: 280px;
  flex-direction: column;
  gap: 10px;
  overflow: auto;
}

.search-result-item,
.selected-stock-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.03);
  padding: 14px 16px;
  color: var(--text-primary);
  text-align: left;
}

.search-result-item {
  transition: border-color 160ms ease, background 160ms ease, transform 160ms ease;
}

.search-result-item:hover {
  border-color: rgba(103, 183, 255, 0.2);
  background: rgba(103, 183, 255, 0.08);
  transform: translateY(-1px);
}

.search-result-name,
.selected-stock-name {
  font-size: 15px;
  font-weight: 600;
}

.search-result-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
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

.field-textarea {
  width: 100%;
  min-height: 112px;
  resize: vertical;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.03);
  color: var(--text-primary);
  padding: 12px 14px;
  outline: none;
  transition: border-color 180ms ease, box-shadow 180ms ease, background 180ms ease;
}

.field-textarea:focus {
  border-color: rgba(103, 183, 255, 0.5);
  box-shadow: 0 0 0 4px rgba(103, 183, 255, 0.1);
}

.analysis-output {
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(5, 11, 20, 0.42);
  padding: 20px;
  color: var(--text-primary);
}

.workflow-grid {
  display: grid;
  gap: 12px;
}

@media (min-width: 768px) {
  .workflow-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

.workflow-step,
.confirmation-card {
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.03);
  padding: 16px;
}

.workflow-title {
  margin-top: 8px;
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 700;
}

.workflow-copy {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.confirmation-card {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.streaming-indicator {
  margin-bottom: 14px;
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.chat-shell {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.chat-list {
  display: flex;
  max-height: 560px;
  flex-direction: column;
  gap: 14px;
  overflow: auto;
  padding-right: 4px;
}

.chat-message {
  max-width: min(860px, 92%);
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  padding: 16px 18px;
}

.chat-message.user {
  align-self: flex-end;
  background: rgba(103, 183, 255, 0.12);
  border-color: rgba(103, 183, 255, 0.22);
}

.chat-message.assistant {
  align-self: flex-start;
  background: rgba(255, 255, 255, 0.03);
}

.chat-role {
  margin-bottom: 8px;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.markdown-body {
  line-height: 1.8;
  word-break: break-word;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  margin: 0 0 12px;
  line-height: 1.3;
  letter-spacing: -0.03em;
}

.markdown-body :deep(h1) {
  font-size: 28px;
}

.markdown-body :deep(h2) {
  font-size: 22px;
}

.markdown-body :deep(h3) {
  font-size: 18px;
}

.markdown-body :deep(p),
.markdown-body :deep(ul),
.markdown-body :deep(ol),
.markdown-body :deep(blockquote),
.markdown-body :deep(pre) {
  margin: 0 0 14px;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 20px;
}

.markdown-body :deep(li + li) {
  margin-top: 6px;
}

.markdown-body :deep(blockquote) {
  border-left: 3px solid rgba(103, 183, 255, 0.38);
  margin-left: 0;
  padding-left: 14px;
  color: var(--text-secondary);
}

.markdown-body :deep(pre) {
  overflow: auto;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  background: rgba(2, 7, 14, 0.9);
  padding: 14px 16px;
}

.markdown-body :deep(code) {
  font-family: 'IBM Plex Mono', 'SFMono-Regular', ui-monospace, monospace;
  font-size: 12px;
}

.markdown-body :deep(:not(pre) > code) {
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.06);
  padding: 2px 6px;
  color: #d6ebff;
}

.markdown-body :deep(a) {
  color: #8cc8ff;
  text-decoration: underline;
  text-decoration-color: rgba(140, 200, 255, 0.4);
}

.chat-composer {
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  padding-top: 16px;
}

.chat-textarea {
  min-height: 124px;
}

.chat-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 12px;
}

@media (max-width: 768px) {
  .search-result-item,
  .selected-stock-card,
  .chat-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .chat-message {
    max-width: 100%;
  }
}
</style>
