import apiClient from './client'
import type {
  CreateDocumentRequest,
  DocumentDetailResponse,
  DocumentResponse,
  ScoredChunkResponse,
  SearchRequest,
} from '@/types/api'

export interface DocumentListParams {
  status?: string
  limit?: number
  offset?: number
}

export const ragApi = {
  async createDocument(payload: CreateDocumentRequest): Promise<{ document_id: number; is_new: boolean; message: string }> {
    const { data } = await apiClient.post('/knowledge-base/documents', payload)
    return data
  },

  async listDocuments(params: DocumentListParams = {}): Promise<DocumentResponse[]> {
    const { data } = await apiClient.get<DocumentResponse[]>('/knowledge-base/documents', { params })
    return data
  },

  async getDocument(id: number): Promise<DocumentDetailResponse> {
    const { data } = await apiClient.get<DocumentDetailResponse>(`/knowledge-base/documents/${id}`)
    return data
  },

  async deleteDocument(id: number): Promise<void> {
    await apiClient.post(`/knowledge-base/documents/${id}/delete`)
  },

  async search(payload: SearchRequest): Promise<ScoredChunkResponse[]> {
    const { data } = await apiClient.post<ScoredChunkResponse[]>('/knowledge-base/search', payload)
    return data
  },
}
