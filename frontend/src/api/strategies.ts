import { apiClient } from './client'

export const fetchStrategies = async () => {
  const { data } = await apiClient.get('/strategies')
  return data
}
