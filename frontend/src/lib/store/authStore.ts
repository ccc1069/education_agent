import { create } from 'zustand'
import type { User } from '@/types/user'

const STORAGE_KEY = 'lumen.auth'

interface PersistedAuth {
  token: string
  refreshToken: string
  user: User
}

function loadFromStorage(): PersistedAuth | null {
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as PersistedAuth
    if (parsed.token && parsed.refreshToken && parsed.user) return parsed
    return null
  } catch {
    return null
  }
}

function saveToStorage(auth: PersistedAuth | null) {
  if (auth) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(auth))
  } else {
    localStorage.removeItem(STORAGE_KEY)
  }
}

interface AuthState {
  token: string | null
  refreshToken: string | null
  user: User | null
  isAuthenticated: boolean
  init: () => void
  login: (token: string, refreshToken: string, user: User) => void
  logout: () => void
  setUser: (user: User) => void
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  refreshToken: null,
  user: null,
  isAuthenticated: false,

  init: () => {
    const persisted = loadFromStorage()
    if (persisted) {
      set({
        token: persisted.token,
        refreshToken: persisted.refreshToken,
        user: persisted.user,
        isAuthenticated: true,
      })
    }
  },

  login: (token, refreshToken, user) => {
    saveToStorage({ token, refreshToken, user })
    set({ token, refreshToken, user, isAuthenticated: true })
  },

  logout: () => {
    saveToStorage(null)
    set({ token: null, refreshToken: null, user: null, isAuthenticated: false })
  },

  setUser: (user) => {
    set((state) => {
      if (!state.token || !state.refreshToken) return state
      const prev = state.user
      if (
        prev &&
        prev.id === user.id &&
        prev.email === user.email &&
        prev.role === user.role &&
        prev.learner_id === user.learner_id &&
        prev.name === user.name
      ) {
        return state
      }
      const persisted: PersistedAuth = { token: state.token, refreshToken: state.refreshToken, user }
      saveToStorage(persisted)
      return { user }
    })
  },
}))
