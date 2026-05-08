import axios, { AxiosError } from 'axios'
import { ElMessage } from 'element-plus'

import { getApiErrorMessage } from '../utils/http'

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api/v1',
  timeout: 10000,
})

apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  },
)

apiClient.interceptors.response.use(
  (response) => {
    return response
  },
  (error: AxiosError) => {
    const message = getApiErrorMessage(error, '请求失败')
    
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
      return Promise.reject(error)
    }
    
    if (error.response?.status === 500) {
      ElMessage.error('服务器内部错误')
    }
    
    return Promise.reject(error)
  },
)

const MAX_RETRIES = 2
const RETRY_DELAY = 1000

export async function requestWithRetry<T>(
  requestFn: () => Promise<T>,
  maxRetries = MAX_RETRIES,
): Promise<T> {
  let lastError: unknown
  
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await requestFn()
    } catch (error) {
      lastError = error
      if (axios.isAxiosError(error) && error.response) {
        const status = error.response.status
        if (status >= 400 && status < 500) {
          throw error
        }
      }
      if (attempt < maxRetries) {
        await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY * (attempt + 1)))
      }
    }
  }
  
  throw lastError
}
