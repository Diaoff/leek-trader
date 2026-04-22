import axios from 'axios'

export function getApiErrorMessage(error: unknown, fallback = '请求失败'): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string' && detail.trim() !== '') {
      return detail
    }

    const message = error.response?.data?.message
    if (typeof message === 'string' && message.trim() !== '') {
      return message
    }

    if (typeof error.message === 'string' && error.message.trim() !== '') {
      return error.message
    }
  }

  if (error instanceof Error && error.message.trim() !== '') {
    return error.message
  }

  return fallback
}
