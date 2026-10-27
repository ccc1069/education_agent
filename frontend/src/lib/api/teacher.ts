import apiClient from './client'
import type {
  AssignmentSummary,
  ClassDetail,
  ClassSummary,
  CreateAssignmentRequest,
  DashboardResponse,
  MemberInfo,
  UpdateAssignmentRequest,
} from '@/types/api'

export const teacherApi = {
  // ---------- Classes ----------
  async createClass(payload: { name: string; description?: string }): Promise<ClassSummary> {
    const { data } = await apiClient.post<ClassSummary>('/teacher/classes', payload)
    return data
  },

  async listClasses(): Promise<ClassSummary[]> {
    const { data } = await apiClient.get<ClassSummary[]>('/teacher/classes')
    return data
  },

  async getClass(id: number): Promise<ClassDetail> {
    const { data } = await apiClient.get<ClassDetail>(`/teacher/classes/${id}`)
    return data
  },

  async joinClass(
    inviteCode: string,
  ): Promise<{ class_id: number; already_member: boolean; name?: string; invite_code?: string }> {
    const { data } = await apiClient.post<{
      class_id: number
      already_member: boolean
      name?: string
      invite_code?: string
    }>('/teacher/classes/join', { invite_code: inviteCode })
    return data
  },

  async listMembers(classId: number): Promise<MemberInfo[]> {
    const { data } = await apiClient.get<MemberInfo[]>(`/teacher/classes/${classId}/members`)
    return data
  },

  async removeMember(classId: number, learnerId: number): Promise<void> {
    await apiClient.post(`/teacher/classes/${classId}/members/${learnerId}/delete`)
  },

  async archiveClass(classId: number): Promise<ClassSummary> {
    const { data } = await apiClient.post<ClassSummary>(`/teacher/classes/${classId}/archive`)
    return data
  },

  async dashboard(classId: number): Promise<DashboardResponse> {
    const { data } = await apiClient.get<DashboardResponse>(`/teacher/classes/${classId}/dashboard`)
    return data
  },

  // ---------- Assignments ----------
  async createAssignment(payload: CreateAssignmentRequest): Promise<AssignmentSummary> {
    const { data } = await apiClient.post<AssignmentSummary>('/teacher/assignments', payload)
    return data
  },

  async listAssignments(params: { status?: string; class_id?: number } = {}): Promise<AssignmentSummary[]> {
    const { data } = await apiClient.get<AssignmentSummary[]>('/teacher/assignments', { params })
    return data
  },

  /** 学生: 所在班级已发布/已关闭的作业 */
  async listMyAssignments(): Promise<AssignmentSummary[]> {
    const { data } = await apiClient.get<AssignmentSummary[]>('/teacher/assignments/mine')
    return data
  },

  async getAssignment(id: number): Promise<AssignmentSummary> {
    const { data } = await apiClient.get<AssignmentSummary>(`/teacher/assignments/${id}`)
    return data
  },

  async updateAssignment(id: number, payload: UpdateAssignmentRequest): Promise<AssignmentSummary> {
    const { data } = await apiClient.post<AssignmentSummary>(`/teacher/assignments/${id}`, payload)
    return data
  },

  async patchAssignmentStatus(id: number, new_status: 'published' | 'closed' | 'archived'): Promise<AssignmentSummary> {
    const { data } = await apiClient.post<AssignmentSummary>(`/teacher/assignments/${id}/status`, { new_status })
    return data
  },

  async removeAssignment(id: number): Promise<void> {
    await apiClient.post(`/teacher/assignments/${id}/delete`)
  },
}
