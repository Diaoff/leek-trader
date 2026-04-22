import { apiClient } from './client'

export interface AccountItem {
  id: number
  tenant_id: string
  name: string
  currency: string
  status: 'active' | 'paused'
  initial_cash: string
  available_cash: string
  frozen_cash: string
  total_equity: string
}

export async function fetchAccounts(): Promise<AccountItem[]> {
  const { data } = await apiClient.get('/accounts')
  return data
}
