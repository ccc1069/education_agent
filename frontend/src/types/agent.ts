/** Agent 事件相关类型 */

export type AgentSource =
  | 'AssessmentAgent'
  | 'TutorAgent'
  | 'CurriculumAgent'
  | 'HintAgent'
  | 'EngagementAgent'
  | 'CriticAgent'
  | 'DebateAgent'
  | 'api'

export type EventType =
  | 'assessment.completed'
  | 'tutor.teaching_response'
  | 'tutor.teaching_criticized'
  | 'curriculum.path_updated'
  | 'hint.provided'
  | 'engagement.state_changed'
  | 'debate.consensus'
  | 'notification'
  | 'error'
  | string

export interface AgentEvent {
  event_type: EventType
  source: AgentSource
  data: Record<string, unknown>
  timestamp: string
}

/** 界面展示用中文名 */
export const AGENT_LABELS: Record<AgentSource, string> = {
  AssessmentAgent: '评估',
  TutorAgent: '导师',
  CurriculumAgent: '课程',
  HintAgent: '提示',
  EngagementAgent: '专注',
  CriticAgent: '评审',
  DebateAgent: '辩论',
  api: '系统',
}

export const AGENT_DESCRIPTIONS: Record<AgentSource, string> = {
  AssessmentAgent: 'BKT 知识掌握评估',
  TutorAgent: '苏格拉底式教学',
  CurriculumAgent: 'SM-2 学习路径规划',
  HintAgent: '三级分级提示',
  EngagementAgent: '学习状态监测',
  CriticAgent: 'LLM 评审与自反思',
  DebateAgent: '多 Agent 协商辩论',
  api: '系统消息',
}

export const AGENT_COLORS: Record<AgentSource, string> = {
  AssessmentAgent: '#3B82F6',
  TutorAgent: '#10B981',
  CurriculumAgent: '#F59E0B',
  HintAgent: '#8B5CF6',
  EngagementAgent: '#F43F5E',
  CriticAgent: '#1B4332',
  DebateAgent: '#D97757',
  api: '#6B7280',
}

/** 事件类型中文(与后端 EventType 对齐) */
export const EVENT_TYPE_LABELS: Record<string, string> = {
  'student.submission': '学生提交',
  'student.question': '学生提问',
  'student.message': '学生消息',
  'assessment.complete': '评估完成',
  'assessment.completed': '评估完成',
  'assessment.mastery_updated': '掌握度更新',
  'assessment.weakness_detected': '薄弱点检出',
  'tutor.teaching_response': '教学回复',
  'tutor.teaching_criticized': '教学评审',
  'tutor.hint_needed': '需要提示',
  'tutor.difficulty_adjusted': '难度调整',
  'tutor.debate_consensus': '辩论共识',
  'curriculum.path_updated': '路径更新',
  'curriculum.review_scheduled': '复习安排',
  'curriculum.next_topic': '下一主题',
  'hint.response': '提示回复',
  'hint.provided': '给出提示',
  'engagement.alert': '专注告警',
  'engagement.encouragement': '鼓励反馈',
  'engagement.pace_adjustment': '节奏调整',
  'engagement.state_changed': '状态变化',
  'debate.consensus': '辩论共识',
  notification: '通知',
  error: '错误',
}

/** 教学水平中文 */
export const LEVEL_LABELS: Record<string, string> = {
  beginner: '入门',
  developing: '发展中',
  intermediate: '中级',
  proficient: '熟练',
  advanced: '进阶',
  mastered: '精通',
  expert: '专家',
}

/** 6 种学习状态(EngagementAgent) */
export type EngagementState =
  | 'focused'
  | 'struggling'
  | 'frustrated'
  | 'bored'
  | 'fatigued'
  | 'idle'

export const ENGAGEMENT_LABELS: Record<EngagementState, string> = {
  focused: '专注',
  struggling: '挣扎',
  frustrated: '挫败',
  bored: '无聊',
  fatigued: '疲劳',
  idle: '空闲',
}

export function eventTypeLabel(eventType: string): string {
  return EVENT_TYPE_LABELS[eventType] ?? eventType.replace(/[._]/g, ' ')
}

export function levelLabel(level: string): string {
  return LEVEL_LABELS[level] ?? level
}
