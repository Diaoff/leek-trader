import { apiClient } from './client'
import type {
  AiAgentRunRequest,
  AiAgentRunResponse,
  AiChatMessage,
  AiChatResponse,
  AiConfig,
  AiConfigPayload,
  AiParameterAdviceRequest,
  AiParameterAdviceResponse,
  AiStockAnalysis,
} from '../types/ai'

const AI_REQUEST_TIMEOUT = 180000
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

export interface AiStreamChunkEvent {
  type: 'chunk'
  content: string
}

export interface AiStreamMetaEvent {
  type: 'meta'
  payload: Record<string, unknown>
}

export interface AiStreamDoneEvent {
  type: 'done'
  payload: Record<string, unknown>
}

export interface AiStreamErrorEvent {
  type: 'error'
  detail: string | Record<string, unknown>
}

export type AiStreamEvent =
  | AiStreamChunkEvent
  | AiStreamMetaEvent
  | AiStreamDoneEvent
  | AiStreamErrorEvent

export async function fetchAiConfig(): Promise<AiConfig> {
  const { data } = await apiClient.get('/ai/config')
  return data
}

export async function updateAiConfig(payload: AiConfigPayload): Promise<AiConfig> {
  const { data } = await apiClient.put('/ai/config', payload)
  return data
}

export async function sendAiChat(messages: AiChatMessage[]): Promise<AiChatResponse> {
  const { data } = await apiClient.post(
    '/ai/chat',
    { messages },
    { timeout: AI_REQUEST_TIMEOUT },
  )
  return data
}

export async function analyzeAiStock(symbol: string, note?: string): Promise<AiStockAnalysis> {
  const { data } = await apiClient.post(
    '/ai/analyze-stock',
    {
      symbol,
      note: note?.trim() ? note.trim() : null,
    },
    { timeout: AI_REQUEST_TIMEOUT },
  )
  return data
}

export async function runAiAgent(payload: AiAgentRunRequest): Promise<AiAgentRunResponse> {
  const { data } = await apiClient.post('/ai/agents/run', payload, { timeout: AI_REQUEST_TIMEOUT })
  return data
}

export async function requestAiParameterAdvice(
  payload: AiParameterAdviceRequest,
): Promise<AiParameterAdviceResponse> {
  const { data } = await apiClient.post('/ai/parameter-advice', payload, { timeout: AI_REQUEST_TIMEOUT })
  return data
}

export async function streamAiChat(
  messages: AiChatMessage[],
  onEvent: (event: AiStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  await streamAiRequest('/ai/chat/stream', { messages }, onEvent, signal)
}

export async function streamAiStockAnalysis(
  symbol: string,
  note: string | undefined,
  onEvent: (event: AiStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  await streamAiRequest(
    '/ai/analyze-stock/stream',
    {
      symbol,
      note: note?.trim() ? note.trim() : null,
    },
    onEvent,
    signal,
  )
}

async function streamAiRequest(
  path: string,
  payload: Record<string, unknown>,
  onEvent: (event: AiStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = localStorage.getItem('token')
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
    signal,
  })

  if (response.status === 401) {
    localStorage.removeItem('token')
    window.location.href = '/login'
    throw new Error('登录已过期')
  }

  if (!response.ok) {
    throw new Error(await readErrorMessage(response))
  }

  if (!response.body) {
    throw new Error('流式响应不可用')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }

    buffer += decoder.decode(value, { stream: true })
    const segments = buffer.split('\n\n')
    buffer = segments.pop() ?? ''

    for (const segment of segments) {
      const event = parseSseSegment(segment)
      if (event) {
        onEvent(event)
      }
    }
  }

  if (buffer.trim()) {
    const event = parseSseSegment(buffer)
    if (event) {
      onEvent(event)
    }
  }
}

function parseSseSegment(segment: string): AiStreamEvent | null {
  const lines = segment.split('\n')
  let eventName = 'message'
  const dataLines: string[] = []

  for (const line of lines) {
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim()
      continue
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim())
    }
  }

  if (dataLines.length === 0) {
    return null
  }

  let payload: Record<string, unknown>
  try {
    payload = JSON.parse(dataLines.join('\n'))
  } catch {
    return null
  }

  if (eventName === 'chunk') {
    return {
      type: 'chunk',
      content: String(payload.content ?? ''),
    }
  }

  if (eventName === 'meta') {
    return {
      type: 'meta',
      payload,
    }
  }

  if (eventName === 'done') {
    return {
      type: 'done',
      payload,
    }
  }

  if (eventName === 'error') {
    const detail = payload.detail
    return {
      type: 'error',
      detail: typeof detail === 'string' || isRecord(detail) ? detail : '流式请求失败',
    }
  }

  return null
}

async function readErrorMessage(response: Response): Promise<string> {
  const contentType = response.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) {
    try {
      const payload = (await response.json()) as { detail?: unknown; error?: { message?: string } }
      const detailMessage = formatErrorDetail(payload.detail)
      if (detailMessage) {
        return detailMessage
      }
      if (payload.error?.message) {
        return payload.error.message
      }
    } catch {
      return `请求失败 (${response.status})`
    }
  }

  const text = await response.text()
  return text || `请求失败 (${response.status})`
}

function formatErrorDetail(detail: unknown): string {
  if (typeof detail === 'string') {
    return detail
  }
  if (typeof detail === 'object' && detail !== null) {
    const row = detail as { message?: unknown; code?: unknown }
    if (typeof row.message === 'string' && row.message.trim()) {
      return row.message
    }
    if (typeof row.code === 'string' && row.code.trim()) {
      return row.code
    }
  }
  return ''
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
