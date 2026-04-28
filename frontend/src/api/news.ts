import { apiClient } from './client'
import type { NewsBriefResponse, NewsFeedResponse } from '../types/news'

export async function fetchMarketNews(limit = 20): Promise<NewsFeedResponse> {
  const { data } = await apiClient.get('/news/market', { params: { limit } })
  return data
}

export async function searchNews(keyword: string, limit = 10): Promise<NewsFeedResponse> {
  const { data } = await apiClient.get('/news/search', { params: { keyword, limit } })
  return data
}

export async function fetchXueqiuNews(limit = 20): Promise<NewsFeedResponse> {
  const { data } = await apiClient.get('/news/xueqiu', { params: { limit } })
  return data
}

export async function fetchNewsBrief(keyword: string, limit = 10): Promise<NewsBriefResponse> {
  const { data } = await apiClient.get('/news/brief', { params: { keyword, limit } })
  return data
}
