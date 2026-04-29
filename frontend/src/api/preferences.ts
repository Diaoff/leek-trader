import { apiClient } from './client'
import type { Preferences, PreferencesUpdatePayload } from '../types/preferences'

export async function fetchPreferences(): Promise<Preferences> {
  const { data } = await apiClient.get('/preferences')
  return data
}

export async function updatePreferences(payload: PreferencesUpdatePayload): Promise<Preferences> {
  const { data } = await apiClient.put('/preferences', payload)
  return data
}
