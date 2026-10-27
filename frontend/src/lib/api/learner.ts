import apiClient from './client'
import type {
  KnowledgeGraphResponse,
  MessageRequest,
  ProgressResponse,
  QuestionRequest,
  SubmitRequest,
  SubmitResponse,
} from '@/types/api'

export const learnerApi = {
  async submit(payload: SubmitRequest): Promise<SubmitResponse> {
    const { data } = await apiClient.post<SubmitResponse>('/submit', payload)
    return data
  },

  async question(payload: QuestionRequest): Promise<SubmitResponse> {
    const { data } = await apiClient.post<SubmitResponse>('/question', payload)
    return data
  },

  async message(payload: MessageRequest): Promise<SubmitResponse> {
    const { data } = await apiClient.post<SubmitResponse>('/message', payload)
    return data
  },

  async progress(learnerPublicId: string): Promise<ProgressResponse> {
    const { data } = await apiClient.get<ProgressResponse>(`/progress/${learnerPublicId}`)
    return data
  },

  async knowledgeGraph(): Promise<KnowledgeGraphResponse> {
    const { data } = await apiClient.get<KnowledgeGraphResponse>('/knowledge-graph')
    return data
  },
}
