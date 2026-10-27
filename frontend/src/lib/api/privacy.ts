import apiClient from './client'
import type {
  ConsentInfo,
  ConsentStatus,
  ConsentType,
  DeletionRequestInfo,
  ExportJobInfo,
} from '@/types/api'

export const privacyApi = {
  // ---------- Consent ----------
  async getConsent(): Promise<ConsentStatus> {
    const { data } = await apiClient.get<ConsentStatus>('/privacy/consent')
    return data
  },

  async updateConsent(consent_type: ConsentType, granted: boolean): Promise<ConsentInfo> {
    const { data } = await apiClient.post<ConsentInfo>('/privacy/consent', { consent_type, granted })
    return data
  },

  // ---------- Export ----------
  async requestExport(): Promise<ExportJobInfo> {
    const { data } = await apiClient.post<ExportJobInfo>('/privacy/export')
    return data
  },

  async listExportJobs(): Promise<ExportJobInfo[]> {
    const { data } = await apiClient.get<ExportJobInfo[]>('/privacy/export/jobs')
    return data
  },

  async downloadExport(jobId: number, filename?: string): Promise<void> {
    const { data } = await apiClient.get(`/privacy/export/${jobId}/download`, {
      responseType: 'blob',
    })
    const blob =
      data instanceof Blob
        ? data
        : new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename ?? `lumen-export-${jobId}.json`
    a.rel = 'noopener'
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },

  // ---------- Deletion ----------
  async requestDeletion(reason: string): Promise<DeletionRequestInfo> {
    const { data } = await apiClient.post<DeletionRequestInfo>('/privacy/delete', { reason })
    return data
  },

  async getDeletionRequest(): Promise<DeletionRequestInfo | null> {
    const { data } = await apiClient.get<DeletionRequestInfo | null>('/privacy/delete')
    return data
  },

  async cancelDeletion(): Promise<DeletionRequestInfo> {
    const { data } = await apiClient.post<DeletionRequestInfo>('/privacy/delete/cancel')
    return data
  },
}
