import apiClient from './client'
import type { TaskExecutionInfo, TaskInfo, TriggerResponse } from '@/types/api'

export interface TaskHistoryParams {
  limit?: number
  offset?: number
  task_name?: string
  status?: string
}

export const tasksApi = {
  async list(): Promise<{ registered: TaskInfo[]; queue_stats: Record<string, unknown> }> {
    const { data } = await apiClient.get('/admin/tasks')
    return data
  },

  async history(params: TaskHistoryParams = {}): Promise<TaskExecutionInfo[]> {
    const { data } = await apiClient.get<TaskExecutionInfo[]>('/admin/tasks/history', { params })
    return data
  },

  async trigger(taskName: string): Promise<TriggerResponse> {
    const { data } = await apiClient.post<TriggerResponse>(`/admin/tasks/trigger/${taskName}`)
    return data
  },

  async run(taskName: string): Promise<TriggerResponse> {
    const { data } = await apiClient.post<TriggerResponse>(`/admin/tasks/${taskName}/run`)
    return data
  },

  async queueStats(): Promise<Record<string, unknown>> {
    const { data } = await apiClient.get('/admin/tasks/queue/stats')
    return data
  },

  async deadLetters(): Promise<unknown[]> {
    const { data } = await apiClient.get<unknown[]>('/admin/tasks/queue/dead-letters')
    return data
  },
}
