export type NewsSource = 'xuangubao' | 'jiuyangongshe' | 'xueqiu'

export interface NewsItem {
  id: string
  source: NewsSource
  title: string
  summary: string
  published_at: string | null
  author: string
  url: string
  symbol_keyword: string
}

export interface NewsFeedResponse {
  items: NewsItem[]
  errors: string[]
}

export interface NewsBriefResponse {
  market: NewsItem[]
  discussions: NewsItem[]
  xueqiu: NewsItem[]
  errors: string[]
}
