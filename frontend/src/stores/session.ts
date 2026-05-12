import { defineStore } from 'pinia'

import { fetchCurrentUser, type CurrentUser } from '../api/auth'

export const useSessionStore = defineStore('session', {
  state: () => ({
    currentUser: null as CurrentUser | null,
    loaded: false,
  }),
  getters: {
    isSuperuser: (state) => state.currentUser?.is_superuser ?? false,
    isAuthenticated: (state) => Boolean(localStorage.getItem('token')),
  },
  actions: {
    async loadCurrentUser(force = false) {
      if (this.loaded && !force) {
        return this.currentUser
      }
      if (!localStorage.getItem('token')) {
        this.currentUser = null
        this.loaded = true
        return null
      }
      try {
        this.currentUser = await fetchCurrentUser()
      } catch {
        this.currentUser = null
      } finally {
        this.loaded = true
      }
      return this.currentUser
    },
    clear() {
      this.currentUser = null
      this.loaded = false
    },
  },
})
