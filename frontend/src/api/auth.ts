import { apiClient } from './client'

export interface AuthToken {
  access_token: string
  token_type: string
}

export interface RegisterPayload {
  username: string
  email: string
  password: string
  full_name?: string
}

export interface CurrentUser {
  id: number
  tenant_id: string
  username: string
  email: string
  full_name: string | null
  is_active: boolean
  is_superuser: boolean
  created_at: string
  updated_at: string
}

export async function login(username: string, password: string): Promise<AuthToken> {
  const body = new URLSearchParams()
  body.set('username', username)
  body.set('password', password)
  const { data } = await apiClient.post<AuthToken>('/auth/login', body, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  return data
}

export async function register(payload: RegisterPayload) {
  const { data } = await apiClient.post('/auth/register', payload)
  return data
}

export async function fetchCurrentUser(): Promise<CurrentUser> {
  const { data } = await apiClient.get('/auth/me')
  return data
}
