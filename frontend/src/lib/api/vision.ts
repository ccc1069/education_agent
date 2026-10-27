import apiClient from './client'
import type { VisionAnalyzeRequest, VisionAnalyzeResponse } from '@/types/api'

export const visionApi = {
  async analyze(payload: VisionAnalyzeRequest): Promise<VisionAnalyzeResponse> {
    const { data } = await apiClient.post<VisionAnalyzeResponse>('/vision/analyze', payload)
    return data
  },
}
