import type {
  AssignmentSummary,
  AuditLogInfo,
  ClassSummary,
  DocumentResponse,
  KnowledgeNode,
  MemberInfo,
  NotificationItem,
  QuestionDetail,
  QuestionSummary,
  TaskInfo,
  TenantSummary,
} from '@/types/api'

// ---------- 知识图谱 ----------
export const mockKnowledgeNodes: KnowledgeNode[] = [
  { id: 'kp_algebra_basics', name: '代数基础', difficulty: 2, prerequisites: [] },
  { id: 'kp_equation_linear', name: '一元一次方程', difficulty: 3, prerequisites: ['kp_algebra_basics'] },
  { id: 'kp_equation_quadratic', name: '一元二次方程', difficulty: 4, prerequisites: ['kp_equation_linear'] },
  { id: 'kp_function_concept', name: '函数概念', difficulty: 3, prerequisites: ['kp_algebra_basics'] },
  { id: 'kp_function_linear', name: '一次函数', difficulty: 3, prerequisites: ['kp_function_concept'] },
  { id: 'kp_function_quadratic', name: '二次函数', difficulty: 5, prerequisites: ['kp_function_concept', 'kp_equation_quadratic'] },
  { id: 'kp_geometry_triangle', name: '三角形', difficulty: 3, prerequisites: [] },
  { id: 'kp_geometry_circle', name: '圆', difficulty: 4, prerequisites: ['kp_geometry_triangle'] },
  { id: 'kp_trigonometry', name: '三角函数', difficulty: 5, prerequisites: ['kp_geometry_triangle', 'kp_function_concept'] },
  { id: 'kp_probability', name: '概率初步', difficulty: 3, prerequisites: ['kp_algebra_basics'] },
  { id: 'kp_statistics', name: '统计', difficulty: 2, prerequisites: ['kp_algebra_basics'] },
  { id: 'kp_sequences', name: '数列', difficulty: 4, prerequisites: ['kp_function_concept'] },
]

export const mockProgress: Record<string, number> = {
  kp_algebra_basics: 0.92,
  kp_equation_linear: 0.85,
  kp_equation_quadratic: 0.62,
  kp_function_concept: 0.78,
  kp_function_linear: 0.71,
  kp_function_quadratic: 0.34,
  kp_geometry_triangle: 0.88,
  kp_geometry_circle: 0.55,
  kp_trigonometry: 0.28,
  kp_probability: 0.66,
  kp_statistics: 0.74,
  kp_sequences: 0.42,
}

// ---------- 用户 ----------
export const mockUsers = {
  student: {
    id: 1001,
    email: 'student@demo.com',
    role: 'student' as const,
    learner_id: 'lrn_demo_student',
    name: '李同学',
  },
  teacher: {
    id: 2001,
    email: 'teacher@demo.com',
    role: 'teacher' as const,
    learner_id: 'lrn_demo_teacher',
    name: '王老师',
  },
  admin: {
    id: 3001,
    email: 'admin@demo.com',
    role: 'admin' as const,
    learner_id: 'lrn_demo_admin',
    name: '管理员',
  },
}

export const mockTokens = {
  access_token: 'mock-jwt-token-for-demo',
  refresh_token: 'mock-refresh-token',
  token_type: 'bearer',
  expires_in: 3600,
}

// ---------- 题目 ----------
export const mockQuestions: QuestionSummary[] = [
  {
    id: 1,
    knowledge_id: 'kp_equation_linear',
    question_type: 'multiple_choice',
    difficulty: 2,
    status: 'published',
    content: {
      question: '解方程 2x + 5 = 11,x 等于多少?',
      options: ['2', '3', '4', '5'],
    },
    created_by: 2001,
    created_at: '2026-07-20T08:00:00Z',
    updated_at: '2026-07-20T08:00:00Z',
  },
  {
    id: 2,
    knowledge_id: 'kp_function_quadratic',
    question_type: 'fill_blank',
    difficulty: 4,
    status: 'published',
    content: { question: '函数 f(x) = x² - 4x + 3 的对称轴是 ____' },
    created_by: 2001,
    created_at: '2026-07-21T10:00:00Z',
    updated_at: '2026-07-21T10:00:00Z',
  },
  {
    id: 3,
    knowledge_id: 'kp_geometry_triangle',
    question_type: 'true_false',
    difficulty: 1,
    status: 'published',
    content: { question: '直角三角形的两个锐角互余' },
    created_by: 2001,
    created_at: '2026-07-22T14:00:00Z',
    updated_at: '2026-07-22T14:00:00Z',
  },
  {
    id: 4,
    knowledge_id: 'kp_probability',
    question_type: 'open_ended',
    difficulty: 3,
    status: 'review',
    content: { question: '抛两枚骰子,点数之和为 7 的概率是多少?请写出推导过程。' },
    created_by: 2001,
    created_at: '2026-07-25T09:00:00Z',
    updated_at: '2026-07-25T09:00:00Z',
  },
  {
    id: 5,
    knowledge_id: 'kp_trigonometry',
    question_type: 'multiple_choice',
    difficulty: 5,
    status: 'draft',
    content: {
      question: 'sin 30° + cos 60° 等于多少?',
      options: ['0.5', '1', '1.5', '2'],
    },
    created_by: 2001,
    created_at: '2026-07-26T11:00:00Z',
    updated_at: '2026-07-26T11:00:00Z',
  },
]

export const mockQuestionDetail: QuestionDetail = {
  ...mockQuestions[0],
  answer: { value: 'B', explanation: '2x = 11 - 5 = 6, x = 3' },
  analysis: '将常数项移到等式右边,然后两边同除以 x 的系数',
}

// ---------- 班级 ----------
export const mockClasses: ClassSummary[] = [
  {
    id: 1,
    name: '高三 (1) 班',
    description: '理科重点班 · 函数与导数专题',
    teacher_id: 2001,
    invite_code: 'CLS-G3MATH-2026',
    is_active: true,
    member_count: 4,
    created_at: '2026-07-01T08:00:00Z',
    updated_at: '2026-07-20T10:00:00Z',
  },
  {
    id: 2,
    name: '高二 (3) 班',
    description: '文科班 · 基础函数复习',
    teacher_id: 2001,
    invite_code: 'CLS-G2ART-2026',
    is_active: true,
    member_count: 2,
    created_at: '2026-07-05T09:00:00Z',
    updated_at: '2026-07-22T14:00:00Z',
  },
]

export const mockMembers: MemberInfo[] = [
  { learner_id: 1001, public_id: 'lrn_demo_student', name: '李同学', joined_at: '2026-07-02T08:00:00Z' },
  { learner_id: 1002, public_id: 'lrn_7a3b9c', name: '张同学', joined_at: '2026-07-03T10:00:00Z' },
  { learner_id: 1003, public_id: 'lrn_8c2d1e', name: '王同学', joined_at: '2026-07-04T11:00:00Z' },
  { learner_id: 1004, public_id: 'lrn_9f4g5h', name: '赵同学', joined_at: '2026-07-06T14:00:00Z' },
]

// ---------- 作业 ----------
export const mockAssignments: AssignmentSummary[] = [
  {
    id: 1,
    title: '第三章函数练习',
    description: '一次函数与二次函数综合练习',
    class_id: 1,
    teacher_id: 2001,
    question_ids: [1, 2, 3],
    status: 'published',
    due_at: '2026-08-05T23:59:00Z',
    created_at: '2026-07-25T08:00:00Z',
    updated_at: '2026-07-25T08:00:00Z',
  },
  {
    id: 2,
    title: '几何复习作业',
    description: '三角形与圆的基础题',
    class_id: 1,
    teacher_id: 2001,
    question_ids: [3],
    status: 'draft',
    due_at: null,
    created_at: '2026-07-26T10:00:00Z',
    updated_at: '2026-07-26T10:00:00Z',
  },
]

// ---------- RAG 文档 ----------
export const mockDocuments: DocumentResponse[] = [
  {
    id: 1,
    title: '贝叶斯知识追踪原理',
    source_type: 'text',
    source_url: null,
    status: 'indexed',
    total_chunks: 12,
    content_hash: 'a3b4c5d6e7f8',
    created_at: '2026-07-10T08:00:00Z',
    error_message: null,
  },
  {
    id: 2,
    title: 'SM-2 间隔重复算法详解',
    source_type: 'markdown',
    source_url: null,
    status: 'indexed',
    total_chunks: 8,
    content_hash: 'b4c5d6e7f8g9',
    created_at: '2026-07-12T10:00:00Z',
    error_message: null,
  },
  {
    id: 3,
    title: '认知负荷理论',
    source_type: 'url',
    source_url: 'https://example.com/cog-load',
    status: 'indexing',
    total_chunks: 0,
    content_hash: null,
    created_at: '2026-07-27T14:00:00Z',
    error_message: null,
  },
]

// ---------- 通知 ----------
export const mockNotifications: NotificationItem[] = [
  {
    id: 1,
    user_id: 1001,
    type: 'review_reminder',
    channel: 'ws',
    title: '复习提醒:二次函数',
    body: '根据 SM-2 算法,今天是你复习"二次函数"的最佳时间,点击前往学习',
    priority: 1,
    status: 'unread',
    created_at: '2026-07-28T09:00:00Z',
    read_at: null,
    payload: { knowledge_id: 'kp_function_quadratic' },
  },
  {
    id: 2,
    user_id: 1001,
    type: 'teacher_feedback',
    channel: 'ws',
    title: '王老师反馈了你的作业',
    body: '第三章函数练习 · 第二题解析有进步,但对称轴公式需再巩固',
    priority: 2,
    status: 'unread',
    created_at: '2026-07-27T16:00:00Z',
    read_at: null,
    payload: { assignment_id: 1 },
  },
  {
    id: 3,
    user_id: 1001,
    type: 'class_event',
    channel: 'ws',
    title: '新作业已布置',
    body: '高三 (1) 班 · 第三章函数练习,截止时间 8 月 5 日',
    priority: 1,
    status: 'read',
    created_at: '2026-07-25T08:00:00Z',
    read_at: '2026-07-25T10:00:00Z',
    payload: { class_id: 1, assignment_id: 1 },
  },
  {
    id: 4,
    user_id: 1001,
    type: 'system',
    channel: 'ws',
    title: '系统维护通知',
    body: '本周日凌晨 2-4 点系统维护,期间无法访问',
    priority: 0,
    status: 'read',
    created_at: '2026-07-22T12:00:00Z',
    read_at: '2026-07-22T12:30:00Z',
    payload: {},
  },
]

// ---------- 租户 ----------
export const mockTenants: TenantSummary[] = [
  { id: 1, name: '示范学校', slug: 'demo-school', plan: 'enterprise', is_active: true },
  { id: 2, name: '实验中学', slug: 'exp-middle', plan: 'pro', is_active: true },
  { id: 3, name: '培训机构 A', slug: 'org-a', plan: 'free', is_active: false },
]

// ---------- 审计日志 ----------
export const mockAuditLogs: AuditLogInfo[] = [
  {
    id: 5,
    actor: 'admin@demo.com',
    action: 'update',
    target: 'tenant/1',
    ip: '192.168.1.10',
    user_agent: 'Mozilla/5.0',
    metadata: { field: 'quota.max_users', old: 100, new: 200 },
    created_at: '2026-07-28T08:30:00Z',
    prev_hash: 'c4d5e6f7g8h9i0j1',
    curr_hash: 'd5e6f7g8h9i0j1k2',
  },
  {
    id: 4,
    actor: 'teacher@demo.com',
    action: 'create',
    target: 'assignment/1',
    ip: '192.168.1.20',
    user_agent: 'Mozilla/5.0',
    metadata: { title: '第三章函数练习', class_id: 1 },
    created_at: '2026-07-25T08:00:00Z',
    prev_hash: 'b3c4d5e6f7g8h9',
    curr_hash: 'c4d5e6f7g8h9i0j1',
  },
  {
    id: 3,
    actor: 'student@demo.com',
    action: 'submit',
    target: 'question/1',
    ip: '192.168.1.30',
    user_agent: 'Mozilla/5.0',
    metadata: { is_correct: true, time_spent: 45 },
    created_at: '2026-07-24T10:00:00Z',
    prev_hash: 'a2b3c4d5e6f7g8',
    curr_hash: 'b3c4d5e6f7g8h9',
  },
  {
    id: 2,
    actor: 'teacher@demo.com',
    action: 'login',
    target: null,
    ip: '192.168.1.20',
    user_agent: 'Mozilla/5.0',
    metadata: {},
    created_at: '2026-07-24T07:00:00Z',
    prev_hash: 'z1y2x3w4v5u6t7',
    curr_hash: 'a2b3c4d5e6f7g8',
  },
  {
    id: 1,
    actor: 'system',
    action: 'create',
    target: 'tenant/1',
    ip: null,
    user_agent: null,
    metadata: { name: '示范学校' },
    created_at: '2026-07-01T00:00:00Z',
    prev_hash: null,
    curr_hash: 'z1y2x3w4v5u6t7',
  },
]

// ---------- 任务 ----------
export const mockTasks: TaskInfo[] = [
  {
    name: 'engagement_monitor',
    description: 'Engagement Agent 监控所有活跃学习者的状态,识别受挫/脱离',
    category: 'engagement',
    schedule: '*/5 * * * *',
  },
  {
    name: 'spaced_repetition_reminder',
    description: '基于 SM-2 算法,为到期的知识点生成复习提醒通知',
    category: 'curriculum',
    schedule: '0 9 * * *',
  },
  {
    name: 'rag_reindex',
    description: '重新索引 pending 状态的 RAG 文档',
    category: 'rag',
    schedule: '0 */6 * * *',
  },
  {
    name: 'audit_log_cleanup',
    description: '清理超过保留期限的审计日志(默认 90 天)',
    category: 'cleanup',
    schedule: '0 2 * * 0',
  },
  {
    name: 'daily_progress_report',
    description: '每日生成班级学习进度报告并推送给教师',
    category: 'analytics',
    schedule: '0 18 * * *',
  },
]
