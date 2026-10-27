import apiClient from './client'
import type {
  CheckAnswerRequest,
  CheckAnswerResponse,
  GenerateQuestionRequest,
  GenerateQuestionResponse,
  QuestionDetail,
  QuestionStatus,
  QuestionSummary,
  QuestionType,
} from '@/types/api'

export interface QuestionListParams {
  status?: QuestionStatus
  knowledge_id?: string
  question_type?: QuestionType
  difficulty?: number
  limit?: number
  offset?: number
}

function normalizeGenerated(
  data: GenerateQuestionResponse & Partial<QuestionDetail>,
): QuestionDetail & { is_duplicate?: boolean } {
  const id = data.id ?? data.question_id
  return {
    id,
    knowledge_id: data.knowledge_id,
    question_type: data.question_type,
    difficulty: data.difficulty,
    content: data.content,
    status: data.status,
    created_by: data.created_by,
    created_at: data.created_at,
    updated_at: data.updated_at,
    answer: data.answer ?? null,
    analysis: data.analysis ?? null,
    is_duplicate: data.is_duplicate,
  }
}

export const questionsApi = {
  async generate(
    payload: GenerateQuestionRequest,
  ): Promise<QuestionDetail & { is_duplicate?: boolean }> {
    const { data } = await apiClient.post<GenerateQuestionResponse>('/questions/generate', payload)
    return normalizeGenerated(data)
  },

  async list(params: QuestionListParams = {}): Promise<QuestionSummary[]> {
    const { data } = await apiClient.get<QuestionSummary[]>('/questions', { params })
    return data
  },

  async get(id: number): Promise<QuestionDetail> {
    const { data } = await apiClient.get<QuestionDetail>(`/questions/${id}`)
    return data
  },

  async patchStatus(id: number, new_status: QuestionStatus): Promise<QuestionDetail> {
    const { data } = await apiClient.post<QuestionDetail>(`/questions/${id}/status`, { new_status })
    return data
  },

  async remove(id: number): Promise<void> {
    await apiClient.post(`/questions/${id}/delete`)
  },

  async check(id: number, payload: CheckAnswerRequest): Promise<CheckAnswerResponse> {
    const { data } = await apiClient.post<CheckAnswerResponse>(`/questions/${id}/check`, payload)
    return data
  },
}
