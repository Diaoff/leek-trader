import { apiClient } from './client'

export interface HealthResponse {
  status: string
  app: string
  environment: string
  tenant: string
  services: {
    api: string
    database: string
    redis: string
  }
}

export const fetchHealth = async (): Promise<HealthResponse> => {
  const { data } = await apiClient.get('/health')
  return data
}
