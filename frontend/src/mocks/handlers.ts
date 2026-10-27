import { http, HttpResponse, delay } from 'msw'
import {
  mockAssignments,
  mockAuditLogs,
  mockClasses,
  mockDocuments,
  mockKnowledgeNodes,
  mockMembers,
  mockNotifications,
  mockProgress,
  mockQuestionDetail,
  mockQuestions,
  mockTasks,
  mockTenants,
  mockTokens,
  mockUsers,
} from './data'

const BASE = '/api/v1'

// 简易 JWT 模拟
function makeJwt(user: { id: number; email: string; role: string }): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const payload = btoa(
    JSON.stringify({
      sub: String(user.id),
      email: user.email,
      role: user.role,
      iat: Math.floor(Date.now() / 1000),
      exp: Math.floor(Date.now() / 1000) + 3600,
    }),
  )
  return `${header}.${payload}.mock-signature`
}

// 模拟延迟
const LATENCY = 200

export const handlers = [
  // ---------- Auth ----------
  http.post(`${BASE}/auth/login`, async ({ request }) => {
    await delay(LATENCY)
    const body = (await request.json()) as { email: string; password: string }
    const user = Object.values(mockUsers).find((u) => u.email === body.email)
    if (!user || body.password !== 'demo123456') {
      return HttpResponse.json({ detail: '邮箱或密码错误' }, { status: 401 })
    }
    return HttpResponse.json({
      access_token: makeJwt(user),
      refresh_token: mockTokens.refresh_token,
      token_type: 'bearer',
      expires_in: 3600,
      user: { ...user, learner_id: user.learner_id ?? null },
    })
  }),

  http.post(`${BASE}/auth/register`, async ({ request }) => {
    await delay(LATENCY)
    const body = (await request.json()) as { email: string; password: string; name?: string }
    if (mockUsers.student.email === body.email) {
      return HttpResponse.json({ detail: '邮箱已注册' }, { status: 400 })
    }
    const user = {
      id: Math.floor(Math.random() * 10000) + 5000,
      email: body.email,
      role: 'student' as const,
      learner_id: `lrn_${Date.now().toString(36)}`,
      name: body.name ?? '新用户',
    }
    return HttpResponse.json({
      access_token: makeJwt(user),
      refresh_token: mockTokens.refresh_token,
      token_type: 'bearer',
      expires_in: 3600,
      user,
    })
  }),

  http.post(`${BASE}/auth/refresh`, async () => {
    await delay(100)
    return HttpResponse.json({
      access_token: makeJwt(mockUsers.student),
      refresh_token: mockTokens.refresh_token,
      token_type: 'bearer',
      expires_in: 3600,
    })
  }),

  http.post(`${BASE}/auth/logout`, async () => {
    await delay(50)
    return new HttpResponse(null, { status: 204 })
  }),

  http.get(`${BASE}/auth/me`, async ({ request }) => {
    await delay(LATENCY)
    const auth = request.headers.get('Authorization')
    if (!auth?.startsWith('Bearer ')) {
      return HttpResponse.json({ detail: '未授权' }, { status: 401 })
    }
    // 从 JWT payload 还原当前用户，避免教师/管理员被冲成学生后反复 setUser
    try {
      const payload = JSON.parse(atob(auth.slice(7).split('.')[1] ?? '')) as {
        email?: string
      }
      const user = Object.values(mockUsers).find((u) => u.email === payload.email)
      if (user) return HttpResponse.json(user)
    } catch {
      /* fall through */
    }
    return HttpResponse.json(mockUsers.student)
  }),

  // ---------- Learner（路径与 lib/api/learner.ts / 后端 routes 对齐，勿用 /learner 前缀） ----------
  http.get(`${BASE}/knowledge-graph`, async () => {
    await delay(LATENCY)
    return HttpResponse.json({ nodes: mockKnowledgeNodes })
  }),

  http.get(`${BASE}/progress/:id`, async () => {
    await delay(LATENCY)
    const entries = Object.entries(mockProgress)
    return HttpResponse.json({
      learner_id: 'lrn_demo_student',
      progress: mockProgress,
      weak_points: entries
        .filter(([, m]) => m < 0.5)
        .map(([id, m]) => ({ id, mastery: m })),
      strong_points: entries
        .filter(([, m]) => m >= 0.8)
        .map(([id, m]) => ({ id, mastery: m })),
      sm2_queue: mockKnowledgeNodes
        .filter((n) => mockProgress[n.id] < 0.8)
        .slice(0, 5)
        .map((n, i) => ({
          knowledge_id: n.id,
          learning_order: i + 1,
          next_review: new Date(Date.now() + 86400000 * (i + 1)).toISOString(),
          interval: 1 + i,
          ease_factor: 2.5,
          repetition: i,
        })),
      status: 'ok',
    })
  }),

  http.post(`${BASE}/submit`, async ({ request }) => {
    await delay(400)
    const body = (await request.json()) as { knowledge_id: string; is_correct: boolean }
    const oldMastery = mockProgress[body.knowledge_id] ?? 0.3
    const newMastery = body.is_correct
      ? Math.min(1, oldMastery + 0.08)
      : Math.max(0, oldMastery - 0.05)
    mockProgress[body.knowledge_id] = newMastery
    return HttpResponse.json({
      mastery: newMastery,
      transition: body.is_correct ? 'improved' : 'declined',
      sm2_updated: true,
      next_review: new Date(Date.now() + 86400000).toISOString(),
      agent_events: [
        {
          event_id: `evt_${Date.now()}_1`,
          source: 'assessment',
          event_type: 'mastery_update',
          data: { knowledge_id: body.knowledge_id, old_mastery: oldMastery, new_mastery: newMastery },
          timestamp: new Date().toISOString(),
        },
        {
          event_id: `evt_${Date.now()}_2`,
          source: 'tutor',
          event_type: 'message',
          data: {
            response: body.is_correct
              ? '答得好!这道题体现了你对核心概念的扎实掌握。下一步可以尝试更综合的题型。'
              : '别灰心,这道题涉及的关键概念需要再回顾。让我引导你重新理解。',
          },
          timestamp: new Date().toISOString(),
        },
        {
          event_id: `evt_${Date.now()}_3`,
          source: 'curriculum',
          event_type: 'next_review',
          data: {
            next_review: new Date(Date.now() + 86400000).toISOString(),
            interval: 1,
          },
          timestamp: new Date().toISOString(),
        },
        {
          event_id: `evt_${Date.now()}_4`,
          source: 'engagement',
          event_type: 'state_change',
          data: { state: body.is_correct ? 'flow' : 'engaged', confidence: 0.82 },
          timestamp: new Date().toISOString(),
        },
        {
          event_id: `evt_${Date.now()}_5`,
          source: 'hint',
          event_type: 'hint_ready',
          data: { level: 1, hint_text: '考虑从定义出发,逐步推导' },
          timestamp: new Date().toISOString(),
        },
      ],
    })
  }),

  http.post(`${BASE}/question`, async ({ request }) => {
    await delay(600)
    const body = (await request.json()) as { knowledge_id: string; question: string }
    return HttpResponse.json({
      response: `关于"${body.knowledge_id}",这是一个很好的问题。让我用苏格拉底式提问引导你思考:你能先回忆一下相关的基础定义吗?当我们把这个定义的每个条件拆开来看,会发现什么?`,
      agent_events: [
        {
          event_id: `evt_q_${Date.now()}`,
          source: 'tutor',
          event_type: 'message',
          data: { response: '引导式问题已生成' },
          timestamp: new Date().toISOString(),
        },
      ],
    })
  }),

  http.post(`${BASE}/message`, async ({ request }) => {
    await delay(500)
    const body = (await request.json()) as { message: string; knowledge_id?: string }
    return HttpResponse.json({
      response: `我理解你提到的 "${body.message.slice(0, 30)}..."。让我帮你梳理思路:第一步先识别问题类型,第二步回忆相关公式,第三步代入计算。你想从哪一步开始?`,
      agent_events: [
        {
          event_id: `evt_m_${Date.now()}`,
          source: 'tutor',
          event_type: 'message',
          data: { response: '自由对话响应' },
          timestamp: new Date().toISOString(),
        },
      ],
    })
  }),

  // ---------- Questions ----------
  http.get(`${BASE}/questions`, async ({ request }) => {
    await delay(LATENCY)
    const url = new URL(request.url)
    const status = url.searchParams.get('status')
    const knowledgeId = url.searchParams.get('knowledge_id')
    const questionType = url.searchParams.get('question_type')
    let result = [...mockQuestions]
    if (status) result = result.filter((q) => q.status === status)
    if (knowledgeId) result = result.filter((q) => q.knowledge_id === knowledgeId)
    if (questionType) result = result.filter((q) => q.question_type === questionType)
    return HttpResponse.json(result)
  }),

  http.get(`${BASE}/questions/:id`, async ({ params }) => {
    await delay(LATENCY)
    const id = Number(params.id)
    const q = mockQuestions.find((x) => x.id === id)
    if (!q) return HttpResponse.json({ detail: '题目不存在' }, { status: 404 })
    return HttpResponse.json({
      ...q,
      answer: { value: 'B', explanation: '详细答案说明' },
      analysis: '本题考查基础知识,需要熟练掌握相关概念',
    })
  }),

  http.post(`${BASE}/questions/generate`, async ({ request }) => {
    await delay(1200)
    const body = (await request.json()) as {
      knowledge_id: string
      question_type?: string
      difficulty?: number
    }
    const newId = Math.max(...mockQuestions.map((q) => q.id)) + 1
    const newNode = mockKnowledgeNodes.find((n) => n.id === body.knowledge_id)
    const newQ = {
      id: newId,
      knowledge_id: body.knowledge_id,
      question_type: (body.question_type ?? 'multiple_choice') as 'multiple_choice',
      difficulty: body.difficulty ?? 3,
      content: {
        stem: `[LLM 生成] 关于 ${newNode?.name ?? body.knowledge_id} 的练习题`,
        options: ['选项 A', '选项 B', '选项 C', '选项 D'],
      },
      status: 'draft' as const,
      created_by: 2001,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
    mockQuestions.push(newQ)
    return HttpResponse.json({
      ...newQ,
      question_id: newId,
      is_duplicate: false,
      answer: 'A',
      analysis: 'LLM 生成的解析',
      llm_meta: { mock: true },
    })
  }),

  http.post(`${BASE}/questions/:id/status`, async ({ params, request }) => {
    await delay(LATENCY)
    const id = Number(params.id)
    const body = (await request.json()) as { new_status: string }
    const q = mockQuestions.find((x) => x.id === id)
    if (!q) return HttpResponse.json({ detail: '题目不存在' }, { status: 404 })
    q.status = body.new_status as typeof q.status
    q.updated_at = new Date().toISOString()
    return HttpResponse.json({
      ...q,
      answer: { value: 'A' },
      analysis: '解析',
    })
  }),

  http.post(`${BASE}/questions/:id/delete`, async ({ params }) => {
    await delay(LATENCY)
    const id = Number(params.id)
    const idx = mockQuestions.findIndex((x) => x.id === id)
    if (idx >= 0) mockQuestions.splice(idx, 1)
    return new HttpResponse(null, { status: 204 })
  }),

  http.post(`${BASE}/questions/:id/check`, async ({ request }) => {
    await delay(500)
    const body = (await request.json()) as { student_answer: unknown }
    const isCorrect = String(body.student_answer).toLowerCase().includes('b') || body.student_answer === '3'
    return HttpResponse.json({
      is_correct: isCorrect,
      feedback: isCorrect
        ? '回答正确!思路清晰,推导规范'
        : '还需完善,请重新检查计算步骤',
      reference_answer: { value: 'B' },
      llm_meta: { model: 'gpt-4o-mini', tokens: 120 },
    })
  }),

  // ---------- Teacher ----------
  http.get(`${BASE}/teacher/classes`, async () => {
    await delay(LATENCY)
    return HttpResponse.json(mockClasses)
  }),

  http.post(`${BASE}/teacher/classes`, async ({ request }) => {
    await delay(LATENCY)
    const body = (await request.json()) as { name: string; description?: string }
    const newClass = {
      id: Math.max(...mockClasses.map((c) => c.id)) + 1,
      name: body.name,
      description: body.description ?? null,
      teacher_id: 2001,
      invite_code: `CLS-${Date.now().toString(36).toUpperCase()}`,
      is_active: true,
      member_count: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
    mockClasses.push(newClass)
    return HttpResponse.json(newClass)
  }),

  http.get(`${BASE}/teacher/classes/:id`, async ({ params }) => {
    await delay(LATENCY)
    const id = Number(params.id)
    const cls = mockClasses.find((c) => c.id === id)
    if (!cls) return HttpResponse.json({ detail: '班级不存在' }, { status: 404 })
    return HttpResponse.json({ ...cls, members: mockMembers })
  }),

  http.post(`${BASE}/teacher/classes/join`, async ({ request }) => {
    await delay(LATENCY)
    const body = (await request.json()) as { invite_code: string }
    const cls = mockClasses.find((c) => c.invite_code === body.invite_code)
    if (!cls) return HttpResponse.json({ detail: '邀请码无效' }, { status: 404 })
    return HttpResponse.json(cls)
  }),

  http.get(`${BASE}/teacher/classes/:id/members`, async () => {
    await delay(LATENCY)
    return HttpResponse.json(mockMembers)
  }),

  http.post(`${BASE}/teacher/classes/:id/members/:lid/delete`, async ({ params }) => {
    await delay(LATENCY)
    const lid = Number(params.lid)
    const idx = mockMembers.findIndex((m) => m.learner_id === lid)
    if (idx >= 0) mockMembers.splice(idx, 1)
    return new HttpResponse(null, { status: 204 })
  }),

  http.post(`${BASE}/teacher/classes/:id/archive`, async ({ params }) => {
    await delay(LATENCY)
    const id = Number(params.id)
    const cls = mockClasses.find((c) => c.id === id)
    if (cls) {
      cls.is_active = false
      cls.updated_at = new Date().toISOString()
    }
    return HttpResponse.json(cls)
  }),

  http.get(`${BASE}/teacher/classes/:id/dashboard`, async ({ params }) => {
    await delay(LATENCY)
    const id = Number(params.id)
    return HttpResponse.json({
      class_id: id,
      class_name: mockClasses.find((c) => c.id === id)?.name ?? `班级 ${id}`,
      member_count: mockMembers.length,
      total_states: 28,
      avg_mastery: 0.62,
      weak_knowledge_ids: ['kp_function_quadratic', 'kp_trigonometry'],
      interventions: [
        {
          learner_id: 1003,
          public_id: 'lrn_8c2d1e',
          state: 'frustrated',
          mastery: 0.28,
          suggestion: '建议降低题目难度,先从基础概念题入手,重建信心',
        },
        {
          learner_id: 1004,
          public_id: 'lrn_9f4g5h',
          state: 'disengaged',
          mastery: 0.42,
          suggestion: '连续 3 天未学习,可推送趣味应用题激发兴趣',
        },
      ],
    })
  }),

  http.get(`${BASE}/teacher/assignments`, async ({ request }) => {
    await delay(LATENCY)
    const url = new URL(request.url)
    const status = url.searchParams.get('status')
    let result = [...mockAssignments]
    if (status) result = result.filter((a) => a.status === status)
    return HttpResponse.json(result)
  }),

  http.get(`${BASE}/teacher/assignments/mine`, async () => {
    await delay(LATENCY)
    const result = mockAssignments
      .filter((a) => a.status === 'published' || a.status === 'closed')
      .map((a) => ({ ...a, class_name: '演示班级' }))
    return HttpResponse.json(result)
  }),

  http.post(`${BASE}/teacher/assignments`, async ({ request }) => {
    await delay(LATENCY)
    const body = (await request.json()) as {
      title: string
      class_id: number
      question_ids: number[]
      description?: string
      due_at?: string
    }
    const newA = {
      id: Math.max(...mockAssignments.map((a) => a.id)) + 1,
      title: body.title,
      description: body.description ?? null,
      class_id: body.class_id,
      teacher_id: 2001,
      question_ids: body.question_ids,
      status: 'draft' as const,
      due_at: body.due_at ?? null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
    mockAssignments.push(newA)
    return HttpResponse.json(newA)
  }),

  http.post(`${BASE}/teacher/assignments/:id/status`, async ({ params, request }) => {
    await delay(LATENCY)
    const id = Number(params.id)
    const body = (await request.json()) as { new_status: string }
    const a = mockAssignments.find((x) => x.id === id)
    if (!a) return HttpResponse.json({ detail: '作业不存在' }, { status: 404 })
    a.status = body.new_status as typeof a.status
    a.updated_at = new Date().toISOString()
    return HttpResponse.json(a)
  }),

  http.post(`${BASE}/teacher/assignments/:id`, async ({ params, request }) => {
    await delay(LATENCY)
    const id = Number(params.id)
    const body = (await request.json()) as {
      title: string
      class_id?: number
      question_ids: number[]
      description?: string
      due_at?: string | null
    }
    const a = mockAssignments.find((x) => x.id === id)
    if (!a) return HttpResponse.json({ detail: '作业不存在' }, { status: 404 })
    if (a.status === 'archived') {
      return HttpResponse.json({ detail: 'cannot edit archived assignment' }, { status: 400 })
    }
    a.title = body.title
    a.description = body.description ?? null
    a.question_ids = body.question_ids ?? []
    a.due_at = body.due_at ?? null
    if (body.class_id != null && a.status === 'draft') a.class_id = body.class_id
    a.updated_at = new Date().toISOString()
    return HttpResponse.json(a)
  }),

  http.post(`${BASE}/teacher/assignments/:id/delete`, async ({ params }) => {
    await delay(LATENCY)
    const id = Number(params.id)
    const idx = mockAssignments.findIndex((a) => a.id === id)
    if (idx >= 0) mockAssignments.splice(idx, 1)
    return new HttpResponse(null, { status: 204 })
  }),

  // ---------- RAG ----------
  http.get(`${BASE}/knowledge-base/documents`, async () => {
    await delay(LATENCY)
    return HttpResponse.json(mockDocuments)
  }),

  http.get(`${BASE}/knowledge-base/documents/:id`, async ({ params }) => {
    await delay(LATENCY)
    const id = Number(params.id)
    const doc = mockDocuments.find((d) => d.id === id)
    if (!doc) return HttpResponse.json({ detail: '文档不存在' }, { status: 404 })
    return HttpResponse.json({
      ...doc,
      chunks: [
        {
          id: 1,
          document_id: id,
          chunk_index: 0,
          content: `${doc.title} 的示例分块内容。`,
          token_count: 64,
          metadata: {},
        },
      ],
    })
  }),

  http.post(`${BASE}/knowledge-base/documents`, async ({ request }) => {
    await delay(LATENCY)
    const body = (await request.json()) as { title: string; content: string }
    const newDoc = {
      id: Math.max(...mockDocuments.map((d) => d.id)) + 1,
      title: body.title,
      source_type: 'text',
      source_url: null,
      status: 'indexed',
      total_chunks: Math.ceil(body.content.length / 200),
      content_hash: Math.random().toString(36).slice(2, 14),
      created_at: new Date().toISOString(),
      error_message: null,
    }
    mockDocuments.push(newDoc)
    return HttpResponse.json({
      document_id: newDoc.id,
      is_new: true,
      message: `文档已添加,生成 ${newDoc.total_chunks} 个分块`,
    })
  }),

  http.post(`${BASE}/knowledge-base/documents/:id/delete`, async ({ params }) => {
    await delay(LATENCY)
    const id = Number(params.id)
    const idx = mockDocuments.findIndex((d) => d.id === id)
    if (idx >= 0) mockDocuments.splice(idx, 1)
    return new HttpResponse(null, { status: 204 })
  }),

  http.post(`${BASE}/knowledge-base/search`, async ({ request }) => {
    await delay(800)
    const body = (await request.json()) as { query: string; top_k?: number }
    const topK = body.top_k ?? 5
    return HttpResponse.json(
      Array.from({ length: Math.min(topK, 4) }).map((_, i) => ({
        chunk_id: i + 1,
        document_id: 1,
        content: `这是与查询 "${body.query}" 相关的语义片段 #${i + 1}。文档内容基于余弦相似度排序,展示了 RAG 检索的核心原理:将查询向量化后与文档向量比对。`,
        score: 0.92 - i * 0.08,
        chunk_index: i,
        token_count: 120 + i * 15,
        metadata: {},
        document_title: mockDocuments[i % mockDocuments.length].title,
        document_source_type: mockDocuments[i % mockDocuments.length].source_type,
      })),
    )
  }),

  // ---------- Notifications ----------
  http.get(`${BASE}/notifications`, async ({ request }) => {
    await delay(LATENCY)
    return HttpResponse.json({
      items: mockNotifications,
      total: mockNotifications.length,
      total_unread: mockNotifications.filter((n) => n.status === 'unread').length,
    })
  }),

  http.get(`${BASE}/notifications/unread-count`, async () => {
    await delay(100)
    return HttpResponse.json({
      unread: mockNotifications.filter((n) => n.status === 'unread').length,
    })
  }),

  http.post(`${BASE}/notifications/:id/read`, async ({ params }) => {
    await delay(100)
    const id = Number(params.id)
    const n = mockNotifications.find((x) => x.id === id)
    if (n) {
      n.status = 'read'
      n.read_at = new Date().toISOString()
    }
    return HttpResponse.json({ ok: true, id })
  }),

  http.post(`${BASE}/notifications/read-all`, async () => {
    await delay(200)
    let marked = 0
    mockNotifications.forEach((n) => {
      if (n.status === 'unread') {
        n.status = 'read'
        n.read_at = new Date().toISOString()
        marked += 1
      }
    })
    return HttpResponse.json({ ok: true, marked })
  }),

  http.get(`${BASE}/notifications/preferences`, async () => {
    await delay(LATENCY)
    return HttpResponse.json({
      ws_enabled: true,
      email_enabled: false,
      push_enabled: true,
      quiet_hours_start: 22,
      quiet_hours_end: 8,
      min_priority: 0,
    })
  }),

  http.post(`${BASE}/notifications/preferences`, async ({ request }) => {
    await delay(100)
    const body = (await request.json()) as Record<string, unknown>
    return HttpResponse.json({
      ws_enabled: true,
      email_enabled: false,
      push_enabled: true,
      quiet_hours_start: 22,
      quiet_hours_end: 8,
      min_priority: 0,
      ...body,
    })
  }),

  // ---------- Privacy（与 privacy.ts / 后端 privacy_routes 对齐） ----------
  http.get(`${BASE}/privacy/consent`, async () => {
    await delay(LATENCY)
    return HttpResponse.json({
      consents: [
        { consent_type: 'analytics', granted: true, updated_at: '2026-07-15T10:00:00Z' },
        { consent_type: 'llm_training', granted: false, updated_at: '2026-07-15T10:00:00Z' },
        { consent_type: 'marketing', granted: false, updated_at: '2026-07-15T10:00:00Z' },
        { consent_type: 'third_party_share', granted: false, updated_at: '2026-07-15T10:00:00Z' },
      ],
    })
  }),

  http.post(`${BASE}/privacy/consent`, async ({ request }) => {
    await delay(100)
    const body = (await request.json()) as { consent_type: string; granted: boolean }
    return HttpResponse.json({
      consent_type: body.consent_type,
      granted: body.granted,
      updated_at: new Date().toISOString(),
    })
  }),

  http.get(`${BASE}/privacy/export/jobs`, async () => {
    await delay(LATENCY)
    return HttpResponse.json([
      {
        id: 1,
        status: 'completed',
        requested_at: '2026-07-15T10:00:00Z',
        completed_at: '2026-07-15T10:05:00Z',
        file_size_bytes: 245678,
        download_url: '/api/v1/privacy/export/1/download',
      },
    ])
  }),

  http.post(`${BASE}/privacy/export`, async () => {
    await delay(LATENCY)
    const id = Math.floor(Math.random() * 1000) + 100
    return HttpResponse.json({
      id,
      status: 'completed',
      requested_at: new Date().toISOString(),
      completed_at: new Date().toISOString(),
      file_size_bytes: 4096,
      download_url: `/api/v1/privacy/export/${id}/download`,
    })
  }),

  http.get(`${BASE}/privacy/export/:jobId/download`, async ({ params }) => {
    await delay(LATENCY)
    const body = JSON.stringify(
      {
        user: { email: 'student@demo.com' },
        learner: { public_id: 'learner-demo' },
        knowledge_states: [],
        submissions: [],
        exported_at: new Date().toISOString(),
        job_id: Number(params.jobId),
      },
      null,
      2,
    )
    return new HttpResponse(body, {
      headers: {
        'Content-Type': 'application/json',
        'Content-Disposition': `attachment; filename="lumen-export-${params.jobId}.json"`,
      },
    })
  }),

  http.get(`${BASE}/privacy/delete`, async () => {
    await delay(LATENCY)
    return HttpResponse.json(null)
  }),

  http.post(`${BASE}/privacy/delete`, async ({ request }) => {
    await delay(LATENCY)
    const body = (await request.json()) as { reason?: string }
    return HttpResponse.json({
      id: 1,
      status: 'pending',
      reason: body.reason ?? '',
      scheduled_at: new Date(Date.now() + 30 * 86400000).toISOString(),
      created_at: new Date().toISOString(),
    })
  }),

  http.post(`${BASE}/privacy/delete/cancel`, async () => {
    await delay(LATENCY)
    return HttpResponse.json({
      id: 1,
      status: 'cancelled',
      reason: '',
      scheduled_at: null,
      created_at: new Date().toISOString(),
    })
  }),

  // ---------- Vision ----------
  http.post(`${BASE}/vision/analyze`, async () => {
    await delay(1500)
    return HttpResponse.json({
      response:
        '从图片中识别到一道关于二次函数的题目。函数 f(x) = x² - 4x + 3 的对称轴计算如下:\n\n1. 提取系数:a=1, b=-4, c=3\n2. 对称轴公式:x = -b/(2a)\n3. 代入:x = 4/2 = 2\n\n因此对称轴为 x = 2。建议你尝试画图验证,顶点坐标为 (2, -1)。',
      metadata: {
        image_count: 1,
        model: 'gpt-4o',
        tokens: 320,
        processing_time_ms: 1450,
      },
    })
  }),

  // ---------- Admin: Tenants ----------
  http.get(`${BASE}/tenants`, async () => {
    await delay(LATENCY)
    return HttpResponse.json(
      mockTenants.map((t) => ({
        ...t,
        created_at: '2026-07-01T00:00:00Z',
        settings: {},
        user_count: t.id === 1 ? 156 : t.id === 2 ? 89 : 12,
        quota: {
          max_users: t.plan === 'enterprise' ? 100000 : t.plan === 'pro' ? 500 : 50,
          max_llm_tokens_per_month:
            t.plan === 'enterprise' ? 10_000_000 : t.plan === 'pro' ? 500_000 : 10_000,
          current_llm_tokens:
            t.plan === 'enterprise' ? 2840000 : t.plan === 'pro' ? 56000 : 4500,
        },
      })),
    )
  }),

  http.post(`${BASE}/tenants`, async ({ request }) => {
    await delay(LATENCY)
    const body = (await request.json()) as { name: string; slug: string; plan?: string }
    const newT = {
      id: Math.max(...mockTenants.map((t) => t.id)) + 1,
      name: body.name,
      slug: body.slug,
      plan: (body.plan ?? 'free') as 'free',
      is_active: true,
    }
    mockTenants.push(newT)
    return HttpResponse.json(newT)
  }),

  http.post(`${BASE}/tenants/:id`, async ({ params, request }) => {
    await delay(LATENCY)
    const id = Number(params.id)
    const body = (await request.json()) as Record<string, unknown>
    const t = mockTenants.find((x) => x.id === id)
    if (!t) return HttpResponse.json({ detail: '租户不存在' }, { status: 404 })
    Object.assign(t, body)
    return HttpResponse.json({
      ...t,
      created_at: '2026-07-01T00:00:00Z',
      settings: {},
      user_count: 100,
      quota: {
        max_users: 200,
        max_llm_tokens_per_month: 1000000,
        current_llm_tokens: 280000,
      },
    })
  }),

  http.post(`${BASE}/tenants/:id/quota`, async ({ params, request }) => {
    await delay(LATENCY)
    const id = Number(params.id)
    const body = (await request.json()) as { max_users?: number; max_llm_tokens_per_month?: number }
    const t = mockTenants.find((x) => x.id === id)
    if (!t) return HttpResponse.json({ detail: '租户不存在' }, { status: 404 })
    return HttpResponse.json({
      ...t,
      created_at: '2026-07-01T00:00:00Z',
      settings: {},
      user_count: 100,
      quota: {
        max_users: body.max_users ?? 200,
        max_llm_tokens_per_month: body.max_llm_tokens_per_month ?? 1000000,
        current_llm_tokens: 280000,
      },
    })
  }),

  http.post(`${BASE}/tenants/:id/quota/reset`, async ({ params }) => {
    await delay(LATENCY)
    const id = Number(params.id)
    const t = mockTenants.find((x) => x.id === id)
    if (!t) return HttpResponse.json({ detail: '租户不存在' }, { status: 404 })
    return HttpResponse.json({
      ...t,
      created_at: '2026-07-01T00:00:00Z',
      settings: {},
      user_count: 100,
      quota: {
        max_users: 200,
        max_llm_tokens_per_month: 1000000,
        current_llm_tokens: 0,
      },
    })
  }),

  http.post(`${BASE}/tenants/:id/delete`, async ({ params }) => {
    await delay(LATENCY)
    const id = Number(params.id)
    const idx = mockTenants.findIndex((t) => t.id === id)
    if (idx >= 0) mockTenants.splice(idx, 1)
    return new HttpResponse(null, { status: 204 })
  }),

  // ---------- Admin: Audit ----------
  http.get(`${BASE}/audit/logs`, async ({ request }) => {
    await delay(LATENCY)
    const url = new URL(request.url)
    const actor = url.searchParams.get('actor')
    const action = url.searchParams.get('action')
    let result = [...mockAuditLogs]
    if (actor) result = result.filter((l) => l.actor.includes(actor))
    if (action) result = result.filter((l) => l.action.includes(action))
    return HttpResponse.json(result)
  }),

  http.get(`${BASE}/audit/verify`, async () => {
    await delay(LATENCY)
    return HttpResponse.json({
      valid: true,
      checked: mockAuditLogs.length,
      broken_at: null,
    })
  }),

  // ---------- Admin: Tasks ----------
  http.get(`${BASE}/admin/tasks`, async () => {
    await delay(LATENCY)
    return HttpResponse.json({
      registered: mockTasks,
      queue_stats: {
        size: 3,
        processed_today: 247,
        failed_today: 2,
        avg_latency_ms: 320,
      },
    })
  }),

  http.get(`${BASE}/admin/tasks/history`, async ({ request }) => {
    await delay(LATENCY)
    const url = new URL(request.url)
    const status = url.searchParams.get('status')
    const baseHistory = [
      { id: 5, task_name: 'engagement_monitor', status: 'success', started_at: '2026-07-28T08:55:00Z', completed_at: '2026-07-28T08:55:02Z', duration_ms: 2100, error_message: null, metadata: { checked: 156, flagged: 3 }, triggered_by: 'scheduler' },
      { id: 4, task_name: 'spaced_repetition_reminder', status: 'success', started_at: '2026-07-28T09:00:00Z', completed_at: '2026-07-28T09:00:05Z', duration_ms: 5000, error_message: null, metadata: { sent: 42 }, triggered_by: 'scheduler' },
      { id: 3, task_name: 'rag_reindex', status: 'failed', started_at: '2026-07-28T06:00:00Z', completed_at: '2026-07-28T06:00:12Z', duration_ms: 12000, error_message: 'Embedding service timeout', metadata: {}, triggered_by: 'scheduler' },
      { id: 2, task_name: 'engagement_monitor', status: 'success', started_at: '2026-07-28T08:50:00Z', completed_at: '2026-07-28T08:50:02Z', duration_ms: 1900, error_message: null, metadata: { checked: 156, flagged: 2 }, triggered_by: 'scheduler' },
      { id: 1, task_name: 'daily_progress_report', status: 'success', started_at: '2026-07-27T18:00:00Z', completed_at: '2026-07-27T18:00:08Z', duration_ms: 8200, error_message: null, metadata: { reports: 8 }, triggered_by: 'admin@demo.com' },
    ]
    let result = baseHistory
    if (status) result = result.filter((h) => h.status === status)
    return HttpResponse.json(result)
  }),

  http.post(`${BASE}/admin/tasks/trigger/:name`, async ({ params }) => {
    await delay(500)
    return HttpResponse.json({
      task_name: params.name,
      status: 'success',
      result: { triggered: true, queued: true },
    })
  }),

  http.get(`${BASE}/admin/tasks/queue/stats`, async () => {
    await delay(LATENCY)
    return HttpResponse.json({
      size: 3,
      processed_today: 247,
      failed_today: 2,
      avg_latency_ms: 320,
    })
  }),
]
