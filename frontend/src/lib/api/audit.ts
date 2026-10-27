import apiClient from './client'
import type { AuditLogInfo, ChainVerificationResult } from '@/types/api'

export interface AuditLogParams {
  limit?: number
  offset?: number
  actor?: string
  action?: string
}

export const auditApi = {
  async list(params: AuditLogParams = {}): Promise<AuditLogInfo[]> {
    const { data } = await apiClient.get<AuditLogInfo[]>('/audit/logs', { params })
    return data
  },

  async verify(fromLogId?: number): Promise<ChainVerificationResult> {
    const { data } = await apiClient.get<ChainVerificationResult>('/audit/verify', {
      params: fromLogId ? { from_log_id: fromLogId } : {},
    })
    return data
  },
}
