import { defineStore } from 'pinia'

import { fetchPreferences, updatePreferences } from '../api/preferences'
import type { Preferences, PreferencesUpdatePayload } from '../types/preferences'
import { getApiErrorMessage } from '../utils/http'

export const usePreferencesStore = defineStore('preferences', {
  state: () => ({
    preferences: null as Preferences | null,
    loading: false,
    saving: false,
    error: '',
  }),
  actions: {
    async fetchPreferences() {
      this.loading = true
      this.error = ''
      try {
        this.preferences = await fetchPreferences()
      } catch (error: unknown) {
        this.error = getApiErrorMessage(error, '偏好设置加载失败')
      } finally {
        this.loading = false
      }
    },
    async updatePreferences(payload: PreferencesUpdatePayload) {
      this.saving = true
      this.error = ''
      try {
        this.preferences = await updatePreferences(payload)
        return this.preferences
      } catch (error: unknown) {
        this.error = getApiErrorMessage(error, '偏好设置保存失败')
        throw error
      } finally {
        this.saving = false
      }
    },
  },
})
