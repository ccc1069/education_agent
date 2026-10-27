import apiClient from './client'
import type {
  NotificationItem,
  NotificationListResponse,
  NotificationPreferences,
} from '@/types/api'

export interface NotificationListParams {
  limit?: number
  offset?: number
  unread_only?: boolean
}

export const notificationsApi = {
  async list(params: NotificationListParams = {}): Promise<NotificationListResponse> {
    const { data } = await apiClient.get<NotificationListResponse>('/notifications', { params })
    return data
  },

  async unreadCount(): Promise<{ unread: number }> {
    const { data } = await apiClient.get<{ unread: number }>('/notifications/unread-count')
    return data
  },

  async markRead(id: number): Promise<{ ok: boolean; id: number }> {
    const { data } = await apiClient.post(`/notifications/${id}/read`)
    return data
  },

  async markAllRead(): Promise<{ ok: boolean; marked: number }> {
    const { data } = await apiClient.post('/notifications/read-all')
    return data
  },

  async getPreferences(): Promise<NotificationPreferences> {
    const { data } = await apiClient.get<NotificationPreferences>('/notifications/preferences')
    return data
  },

  async updatePreferences(payload: Partial<NotificationPreferences>): Promise<NotificationPreferences> {
    const { data } = await apiClient.post<NotificationPreferences>('/notifications/preferences', payload)
    return data
  },
}

export type { NotificationItem }
