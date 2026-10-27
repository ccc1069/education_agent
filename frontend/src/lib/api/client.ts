import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'

const BASE_URL = '/api/v1'

let isRefreshing = false
let refreshSubscribers: Array<(token: string | null) => void> = []

function subscribeTokenRefresh(cb: (token: string | null) => void) {
  refreshSubscribers.push(cb)
}

function onRefreshed(token: string | null) {
  refreshSubscribers.forEach((cb) => cb(token))
  refreshSubscribers = []
}

function getStoredTokens() {
  const raw = localStorage.getItem('lumen.auth')
  if (!raw) return { token: null, refreshToken: null }
  try {
    const parsed = JSON.parse(raw)
    return { token: parsed.token ?? null, refreshToken: parsed.refreshToken ?? null }
  } catch {
    return { token: null, refreshToken: null }
  }
}

export const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  // Tutor/Critic 会调真实 LLM,默认 30s 容易在代理慢时被前端掐断
  timeout: 90000,
  headers: { 'Content-Type': 'application/json' },
})

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const { token } = getStoredTokens()
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    if (error.response?.status === 401 && !originalRequest._retry) {
      const { refreshToken } = getStoredTokens()
      if (!refreshToken) {
        clearAuthAndRedirect()
        return Promise.reject(error)
      }

      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          subscribeTokenRefresh((newToken) => {
            if (!newToken) {
              reject(error)
              return
            }
            originalRequest.headers.Authorization = `Bearer ${newToken}`
            resolve(apiClient(originalRequest))
          })
        })
      }

      originalRequest._retry = true
      isRefreshing = true
      try {
        const resp = await axios.post(`${BASE_URL}/auth/refresh`, { refresh_token: refreshToken })
        const { access_token, refresh_token: newRefresh } = resp.data
        const raw = localStorage.getItem('lumen.auth')
        const parsed = raw ? JSON.parse(raw) : {}
        parsed.token = access_token
        parsed.refreshToken = newRefresh
        localStorage.setItem('lumen.auth', JSON.stringify(parsed))
        onRefreshed(access_token)
        originalRequest.headers.Authorization = `Bearer ${access_token}`
        return apiClient(originalRequest)
      } catch (err) {
        onRefreshed(null)
        clearAuthAndRedirect()
        return Promise.reject(err)
      } finally {
        isRefreshing = false
      }
    }
    return Promise.reject(error)
  },
)

function clearAuthAndRedirect() {
  localStorage.removeItem('lumen.auth')
  if (window.location.pathname !== '/login') {
    window.location.href = '/login'
  }
}

export default apiClient
