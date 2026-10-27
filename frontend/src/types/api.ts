/** 后端 API 类型镜像(对应 code/python Pydantic models) */

import type { Role, User, RegisterResponse, TokenResponse } from './user'

export type { Role, User, RegisterResponse, TokenResponse }

// ---------- Auth ----------
export interface LoginRequest {
  email: string
  password: string
}

export interface RegisterRequest {
  email: string
  password: string
  name?: string
}

export interface RefreshRequest {
  refresh_token: string
}

// ---------- Learner ----------
export interface SubmitRequest {
  knowledge_id: string
  is_correct: boolean
  time_spent_seconds: number
}

export interface QuestionRequest {
  knowledge_id: string
  question: string
  debate_mode?: boolean
}

export interface MessageRequest {
  message: string
  knowledge_id?: string
}

export interface EventPayload {
  type: string
  source: string
  data: Record<string, unknown>
}

export interface SubmitResponse {
  status: string
  events_triggered: number
  events: EventPayload[]
}

export interface KnowledgeNode {
  id: string
  name: string
  difficulty: number
  prerequisites: string[]
  tags?: string[]
}

export interface KnowledgeGraphResponse {
  nodes: KnowledgeNode[]
  learning_order: string[]
}

export interface KnowledgeMastery {
  id: string
  mastery: number
}

export interface ProgressResponse {
  learner_id: string
  progress?: Record<string, number>
  overall?: {
    total_knowledge_points?: number
    avg_mastery?: number
    total_attempts?: number
    total_correct?: number
    accuracy?: number
    level_distribution?: Record<string, number>
  }
  weak_points?: KnowledgeMastery[]
  strong_points?: KnowledgeMastery[]
  status?: 'no_data'
}

// ---------- RAG ----------
export interface DocumentResponse {
  id: number
  title: string
  source_type: string
  source_url: string | null
  status: string
  total_chunks: number
  content_hash: string | null
  created_at: string
  error_message: string | null
}

export interface DocumentChunkPreview {
  chunk_index: number
  content: string
  token_count: number
}

export interface DocumentDetailResponse extends DocumentResponse {
  metadata: Record<string, unknown>
  updated_at: string
  chunks?: DocumentChunkPreview[]
}

export interface CreateDocumentRequest {
  title: string
  content: string
  source_type?: string
  source_url?: string
  metadata?: Record<string, unknown>
}

export interface ScoredChunkResponse {
  chunk_id: number
  document_id: number
  content: string
  score: number
  chunk_index: number
  token_count: number
  metadata: Record<string, unknown>
  document_title: string
  document_source_type: string
}

export interface SearchRequest {
  query: string
  top_k?: number
  min_score?: number
}

// ---------- Questions ----------
export type QuestionType = 'multiple_choice' | 'fill_blank' | 'true_false' | 'open_ended'
export type QuestionStatus = 'draft' | 'review' | 'published' | 'archived' | 'rejected'

export interface QuestionSummary {
  id: number
  knowledge_id: string
  question_type: QuestionType
  difficulty: number
  content: Record<string, unknown>
  status: QuestionStatus
  created_by: number
  created_at: string
  updated_at: string
}

export interface QuestionDetail extends QuestionSummary {
  answer?: string | Record<string, unknown> | null
  analysis?: string | null
}

export interface GenerateQuestionRequest {
  knowledge_id: string
  question_type?: QuestionType
  difficulty?: number
  use_rag?: boolean
}

export interface GenerateQuestionResponse extends QuestionDetail {
  question_id: number
  is_duplicate: boolean
  llm_meta?: Record<string, unknown>
}

export interface CheckAnswerRequest {
  student_answer: unknown
}

export interface CheckAnswerResponse {
  is_correct: boolean
  feedback: string
  reference_answer: unknown
  llm_meta: Record<string, unknown>
}

// ---------- Teacher ----------
export interface ClassSummary {
  id: number
  name: string
  description: string | null
  teacher_id: number
  invite_code: string
  is_active: boolean
  member_count: number
  created_at: string
  updated_at: string
}

export interface MemberInfo {
  learner_id: number
  public_id: string
  name: string | null
  joined_at: string
}

export interface ClassDetail extends ClassSummary {
  members: MemberInfo[]
}

export interface WeakKnowledgeItem {
  knowledge_id: string
  avg_mastery: number
  student_count: number
}

export interface DashboardIntervention {
  learner_id: number
  knowledge_id: string
  mastery: number
  attempts: number
  recommendation: string
  public_id?: string | null
  name?: string | null
}

export interface DashboardResponse {
  class_id: number
  class_name: string
  member_count: number
  total_states: number
  avg_mastery: number
  weak_knowledge_ids: WeakKnowledgeItem[]
  interventions: DashboardIntervention[]
}

export interface AssignmentSummary {
  id: number
  title: string
  description: string | null
  class_id: number
  teacher_id: number
  question_ids: number[]
  status: 'draft' | 'published' | 'closed' | 'archived'
  due_at: string | null
  created_at: string
  updated_at: string
  class_name?: string | null
}

export interface CreateAssignmentRequest {
  title: string
  class_id: number
  question_ids: number[]
  description?: string
  due_at?: string
}

export interface UpdateAssignmentRequest {
  title: string
  class_id?: number
  question_ids: number[]
  description?: string
  due_at?: string | null
}

// ---------- Vision ----------
export interface VisionAnalyzeRequest {
  images: string[]
  knowledge_id?: string
  learner_message?: string
  level?: 'beginner' | 'developing' | 'proficient' | 'mastered'
  mastery?: number
}

export interface VisionAnalyzeResponse {
  response: string
  metadata: Record<string, unknown>
}

// ---------- Notifications ----------
export type NotificationType =
  | 'review_reminder'
  | 'class_event'
  | 'teacher_feedback'
  | 'system'
export type NotificationChannel = 'ws' | 'email' | 'push'
export type NotificationStatus = 'pending' | 'sent' | 'delivered' | 'read' | 'unread' | 'failed'

export interface NotificationItem {
  id: number
  user_id: number
  type: NotificationType
  channel: NotificationChannel
  status: NotificationStatus
  priority: number
  title: string
  body: string
  payload: Record<string, unknown>
  created_at: string
  read_at: string | null
}

export interface NotificationListResponse {
  items: NotificationItem[]
  total_unread: number
  limit: number
  offset: number
}

export interface NotificationPreferences {
  ws_enabled: boolean
  email_enabled: boolean
  push_enabled: boolean
  quiet_hours_start: number | null
  quiet_hours_end: number | null
  min_priority: number
}

// ---------- Privacy ----------
export type ConsentType = 'analytics' | 'llm_training' | 'marketing' | 'third_party_share'

export interface ConsentStatus {
  analytics: boolean
  llm_training: boolean
  marketing: boolean
  third_party_share: boolean
}

export interface ConsentInfo {
  consent_type: ConsentType
  granted: boolean
  consent_version: string
  created_at: string
}

export interface ExportJobInfo {
  id: number
  user_id: number
  status: string
  requested_at: string
  completed_at: string | null
  download_url: string | null
  file_size_bytes: number | null
  error_message: string | null
}

export interface DeletionRequestInfo {
  id: number
  user_id: number
  status: string
  requested_at: string
  scheduled_at: string
  completed_at: string | null
  cancelled_at: string | null
  reason: string | null
}

// ---------- Audit ----------
export interface AuditLogInfo {
  id: number
  actor: string
  action: string
  target: string | null
  ip: string | null
  user_agent: string | null
  metadata: Record<string, unknown>
  created_at: string
  prev_hash: string | null
  curr_hash: string
}

export interface ChainVerificationResult {
  valid: boolean
  checked: number
  broken_at: number | null
}

// ---------- Tasks ----------
export interface TaskScheduleInfo {
  name?: string
  next_run_at?: string | null
  trigger?: string
  type?: string
  expr?: string
  seconds?: number
  max_retries?: number
}

export interface TaskInfo {
  name: string
  description: string
  category: string
  schedule?: string | TaskScheduleInfo
}

export interface TaskExecutionInfo {
  id: number
  task_name: string
  status: string
  started_at: string
  completed_at: string | null
  duration_ms: number | null
  error_message: string | null
  metadata: Record<string, unknown>
  triggered_by: string
}

export interface TriggerResponse {
  task_name: string
  status: string
  result?: unknown
  error?: string
}

// ---------- Tenants ----------
export type TenantPlan = 'free' | 'pro' | 'enterprise'

export interface TenantQuotaInfo {
  max_users: number
  max_llm_tokens_per_month: number
  /** 后端字段名 */
  current_llm_tokens?: number
  /** 兼容旧 Mock 字段 */
  used_llm_tokens_this_month?: number
  period_start?: string | null
}

export interface TenantSummary {
  id: number
  name: string
  slug: string
  plan: TenantPlan
  is_active: boolean
  user_count?: number
  quota?: TenantQuotaInfo | null
}

export interface TenantDetail extends TenantSummary {
  created_at: string
  settings: Record<string, unknown>
  user_count: number
  quota: TenantQuotaInfo
}

export interface CreateTenantRequest {
  name: string
  slug: string
  plan?: TenantPlan
  settings?: Record<string, unknown>
}

// ---------- Common ----------
export interface PaginationParams {
  limit?: number
  offset?: number
}

export interface ApiError {
  detail: string
}
