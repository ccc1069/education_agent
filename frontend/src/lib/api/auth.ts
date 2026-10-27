import apiClient from './client'
import type {
  LoginRequest,
  RefreshRequest,
  RegisterRequest,
  RegisterResponse,
  TokenResponse,
  User,
} from '@/types/api'

export const authApi = {
  async login(payload: LoginRequest): Promise<TokenResponse> {
    const { data } = await apiClient.post<TokenResponse>('/auth/login', payload)
    return data
  },

  async register(payload: RegisterRequest): Promise<RegisterResponse> {
    const { data } = await apiClient.post<RegisterResponse>('/auth/register', payload)
    return data
  },

  async refresh(payload: RefreshRequest): Promise<TokenResponse> {
    const { data } = await apiClient.post<TokenResponse>('/auth/refresh', payload)
    return data
  },

  async logout(refreshToken: string): Promise<void> {
    await apiClient.post('/auth/logout', { refresh_token: refreshToken }, { validateStatus: () => true })
  },

  async me(): Promise<User> {
    const { data } = await apiClient.get<User>('/auth/me')
    return data
  },
}
