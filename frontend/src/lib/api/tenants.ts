import apiClient from './client'
import type { CreateTenantRequest, TenantDetail, TenantSummary } from '@/types/api'

export const tenantsApi = {
  async create(payload: CreateTenantRequest): Promise<TenantSummary> {
    const { data } = await apiClient.post<TenantSummary>('/tenants', payload)
    return data
  },

  async list(params: { limit?: number; offset?: number } = {}): Promise<TenantSummary[]> {
    const { data } = await apiClient.get<TenantSummary[]>('/tenants', { params })
    return data
  },

  async get(id: number): Promise<TenantDetail> {
    const { data } = await apiClient.get<TenantDetail>(`/tenants/${id}`)
    return data
  },

  async update(
    id: number,
    payload: Partial<{ name: string; plan: 'free' | 'pro' | 'enterprise'; is_active: boolean; settings: Record<string, unknown> }>,
  ): Promise<TenantDetail> {
    const { data } = await apiClient.post<TenantDetail>(`/tenants/${id}`, payload)
    return data
  },

  async remove(id: number): Promise<void> {
    await apiClient.post(`/tenants/${id}/delete`)
  },

  async updateQuota(
    id: number,
    payload: { max_users?: number; max_llm_tokens_per_month?: number },
  ): Promise<TenantDetail> {
    const { data } = await apiClient.post<TenantDetail>(`/tenants/${id}/quota`, payload)
    return data
  },

  async resetQuota(id: number): Promise<TenantDetail> {
    const { data } = await apiClient.post<TenantDetail>(`/tenants/${id}/quota/reset`)
    return data
  },
}
