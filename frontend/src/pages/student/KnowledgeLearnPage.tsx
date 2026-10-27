import { useEffect, useMemo, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Input,
  Row,
  Segmented,
  Skeleton,
  Space,
  Switch,
  Tag,
  Typography,
} from 'antd'
import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  PaperClipOutlined,
  QuestionCircleOutlined,
  SendOutlined,
} from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'motion/react'
import { learnerApi } from '@/lib/api/learner'
import { useWebSocket } from '@/lib/ws/useWebSocket'
import { useAuthStore } from '@/lib/store/authStore'
import { EventStream } from '@/components/agent/EventStream'
import { MasteryBar } from '@/components/learner/MasteryBar'
import { PageHeader } from '@/components/ui/PageHeader'
import type { AgentEvent } from '@/types/agent'
import { knowledgeName } from '@/lib/knowledgeLabel'

const { Text, Title, Paragraph } = Typography
const { TextArea } = Input

type ActionMode = 'submit' | 'question' | 'message'

/** 后端难度多为 0~1 小数,统一展示为 1~5 星级文案 */
function formatDifficulty(raw: number): string {
  const stars = raw <= 1 ? Math.max(1, Math.round(raw * 5)) : Math.min(5, Math.round(raw))
  return `${stars} / 5`
}

export default function KnowledgeLearnPage() {
  const { knowledgeId = 'general' } = useParams()
  const { message } = App.useApp()
  const qc = useQueryClient()
  const user = useAuthStore((s) => s.user)

  const { data: graphData } = useQuery({
    queryKey: ['knowledge-graph'],
    queryFn: () => learnerApi.knowledgeGraph(),
  })

  const { data: progressData } = useQuery({
    queryKey: ['progress', user?.learner_id],
    queryFn: () => learnerApi.progress(user!.learner_id!),
    enabled: !!user?.learner_id,
  })

  const node = useMemo(
    () => graphData?.nodes.find((n) => n.id === knowledgeId),
    [graphData, knowledgeId],
  )

  const mastery = progressData?.status === 'no_data' ? 0 : progressData?.progress?.[knowledgeId] ?? 0

  const { events, status, send } = useWebSocket()

  // 切换知识点时清空事件
  useEffect(() => {
    // events 由 hook 内部管理
  }, [knowledgeId])

  const [actionMode, setActionMode] = useState<ActionMode>('submit')
  const [question, setQuestion] = useState('')
  const [messageText, setMessageText] = useState('')
  const [isCorrect, setIsCorrect] = useState<boolean | null>(null)
  const [timeSpent, setTimeSpent] = useState(30)
  const [debateMode, setDebateMode] = useState(false)

  const submitMutation = useMutation({
    mutationFn: (payload: { knowledge_id: string; is_correct: boolean; time_spent_seconds: number }) =>
      learnerApi.submit(payload),
    onSuccess: (res) => {
      message.success(`已提交 · 触发 ${res.events_triggered} 个 Agent`)
      qc.invalidateQueries({ queryKey: ['progress'] })
    },
  })

  const questionMutation = useMutation({
    mutationFn: (payload: { knowledge_id: string; question: string; debate_mode?: boolean }) =>
      learnerApi.question(payload),
    onSuccess: (res) => {
      message.success(`已提交 · 触发 ${res.events_triggered} 个 Agent`)
    },
  })

  const messageMutation = useMutation({
    mutationFn: (payload: { message: string; knowledge_id: string }) => learnerApi.message(payload),
    onSuccess: (res) => {
      message.success(`已提交 · 触发 ${res.events_triggered} 个 Agent`)
    },
  })

  const handleAction = () => {
    if (actionMode === 'submit') {
      if (isCorrect === null) {
        message.warning('请选择答题结果')
        return
      }
      const payload = {
        action: 'submit',
        knowledge_id: knowledgeId,
        is_correct: isCorrect,
        time_spent_seconds: timeSpent,
      }
      send(payload)
      submitMutation.mutate({
        knowledge_id: knowledgeId,
        is_correct: isCorrect,
        time_spent_seconds: timeSpent,
      })
      setIsCorrect(null)
    } else if (actionMode === 'question') {
      if (!question.trim()) {
        message.warning('请输入问题')
        return
      }
      const payload: Record<string, unknown> = {
        action: 'question',
        knowledge_id: knowledgeId,
        question: question.trim(),
      }
      if (debateMode) payload.debate_mode = true
      send(payload)
      questionMutation.mutate({
        knowledge_id: knowledgeId,
        question: question.trim(),
        debate_mode: debateMode || undefined,
      })
      setQuestion('')
    } else {
      if (!messageText.trim()) {
        message.warning('请输入消息')
        return
      }
      send({ action: 'message', message: messageText.trim(), knowledge_id: knowledgeId })
      messageMutation.mutate({ message: messageText.trim(), knowledge_id: knowledgeId })
      setMessageText('')
    }
  }

  return (
    <div className="max-w-7xl mx-auto">
      <PageHeader
        title={node?.name ?? knowledgeId}
        subtitle={node ? `知识点 · ${node.name}` : '加载知识点中...'}
        loading={!graphData}
        extra={
          <Link to="/learn">
            <Button icon={<ArrowLeftOutlined />}>返回学习中心</Button>
          </Link>
        }
      />

      {node && (
        <Card bordered={false} className="lumen-card mb-4">
          <Row gutter={[24, 16]} align="middle">
            <Col xs={24} md={8}>
              <Text
                type="secondary"
                style={{ fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase' }}
              >
                当前掌握度
              </Text>
              <div className="mt-2">
                <MasteryBar mastery={mastery} />
              </div>
            </Col>
            <Col xs={12} md={6}>
              <Text
                type="secondary"
                style={{ fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase' }}
              >
                难度
              </Text>
              <div style={{ fontSize: 20, fontWeight: 600, fontFamily: 'var(--font-serif)' }}>
                {formatDifficulty(node.difficulty)}
              </div>
            </Col>
            <Col xs={12} md={10}>
              <Text
                type="secondary"
                style={{ fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase' }}
              >
                前置知识
              </Text>
              <div className="mt-1 flex flex-wrap gap-1">
                {node.prerequisites.length === 0 ? (
                  <Text type="secondary" style={{ fontSize: 13 }}>
                    无(可立即开始学习)
                  </Text>
                ) : (
                  node.prerequisites.map((p) => (
                    <Link key={p} to={`/learn/${p}`}>
                      <Tag
                        style={{
                          fontSize: 11,
                          margin: 0,
                          padding: '0 6px',
                          cursor: 'pointer',
                          background: 'var(--color-moss-50)',
                          border: '1px solid var(--color-line)',
                          color: 'var(--color-moss)',
                        }}
                      >
                        {knowledgeName(graphData?.nodes, p)}
                      </Tag>
                    </Link>
                  ))
                )}
              </div>
            </Col>
          </Row>
        </Card>
      )}

      <Row gutter={[16, 16]}>
        {/* 左侧: 操作面板 */}
        <Col xs={24} lg={10}>
          <Card bordered={false} className="lumen-card" style={{ position: 'sticky', top: 80 }}>
            <Title level={5} style={{ marginTop: 0 }}>
              学习操作
            </Title>
            <Segmented
              block
              value={actionMode}
              onChange={(v) => setActionMode(v as ActionMode)}
              options={[
                { label: '提交答题', value: 'submit' },
                { label: '提问', value: 'question' },
                { label: '自由消息', value: 'message' },
              ]}
              style={{ marginBottom: 16 }}
            />

            {actionMode === 'submit' && (
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  选择本题答题结果,系统将更新你的知识掌握度
                </Text>
                <Row gutter={8} className="mt-3">
                  <Col span={12}>
                    <Button
                      block
                      size="large"
                      icon={<CheckCircleOutlined />}
                      onClick={() => setIsCorrect(true)}
                      type={isCorrect === true ? 'primary' : 'default'}
                      style={
                        isCorrect === true
                          ? {}
                          : {
                              borderColor: '#10B981',
                              color: '#10B981',
                            }
                      }
                    >
                      答对了
                    </Button>
                  </Col>
                  <Col span={12}>
                    <Button
                      block
                      size="large"
                      icon={<CloseCircleOutlined />}
                      onClick={() => setIsCorrect(false)}
                      type={isCorrect === false ? 'primary' : 'default'}
                      danger={isCorrect === false}
                    >
                      答错了
                    </Button>
                  </Col>
                </Row>
                <div className="mt-4">
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    用时(秒): {timeSpent}
                  </Text>
                  <input
                    type="range"
                    min={5}
                    max={300}
                    step={5}
                    value={timeSpent}
                    onChange={(e) => setTimeSpent(Number(e.target.value))}
                    style={{ width: '100%', marginTop: 6 }}
                  />
                </div>
              </div>
            )}

            {actionMode === 'question' && (
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  针对该知识点提问,导师 Agent 会用苏格拉底式引导你思考
                </Text>
                <TextArea
                  className="mt-3"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="例如:为什么一元二次方程会有两个解?"
                  autoSize={{ minRows: 4, maxRows: 8 }}
                  maxLength={500}
                  showCount
                />
                <div className="mt-3 flex items-center justify-between">
                  <Space>
                    <Switch
                      size="small"
                      checked={debateMode}
                      onChange={setDebateMode}
                      checkedChildren="Debate"
                      unCheckedChildren="单 Agent"
                    />
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {debateMode ? '多 Agent 辩论(适合复杂概念)' : '默认导师引导'}
                    </Text>
                  </Space>
                </div>
              </div>
            )}

            {actionMode === 'message' && (
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  自由表达你的学习感受或疑问,Engagement Agent 会监测你的学习状态
                </Text>
                <TextArea
                  className="mt-3"
                  value={messageText}
                  onChange={(e) => setMessageText(e.target.value)}
                  placeholder="例如:这章内容有点难,我有点跟不上..."
                  autoSize={{ minRows: 4, maxRows: 8 }}
                  maxLength={500}
                  showCount
                />
              </div>
            )}

            <Button
              type="primary"
              size="large"
              block
              icon={<SendOutlined />}
              className="mt-4"
              loading={
                submitMutation.isPending ||
                questionMutation.isPending ||
                messageMutation.isPending
              }
              onClick={handleAction}
            >
              {actionMode === 'submit'
                ? '提交答题'
                : actionMode === 'question'
                  ? '向导师提问'
                  : '发送消息'}
            </Button>

            {status !== 'open' && (
              <Alert
                type={status === 'connecting' ? 'info' : 'warning'}
                showIcon
                className="mt-3"
                message={
                  status === 'connecting'
                    ? 'WebSocket 连接中…'
                    : status === 'error'
                      ? 'WebSocket 连接失败,将通过 HTTP 提交'
                      : 'WebSocket 未连接,将通过 HTTP 提交(实时事件流不可用)'
                }
                style={{ fontSize: 12 }}
              />
            )}
          </Card>
        </Col>

        {/* 右侧: Agent 事件流 */}
        <Col xs={24} lg={14}>
          <div className="flex items-center justify-between mb-3">
            <Title level={5} style={{ margin: 0 }}>
              Agent 事件流
            </Title>
            <Space>
              <PaperClipOutlined style={{ color: 'var(--color-mist)' }} />
              <Text type="secondary" style={{ fontSize: 12 }}>
                {events.length} 条事件
              </Text>
            </Space>
          </div>
          <EventStream
            events={events}
            status={status}
            emptyHint="点击左侧操作按钮,5+2 Agent 将协同响应"
          />

          {/* Agent 介绍 */}
          <Card bordered={false} className="lumen-card mt-4" size="small">
            <Text
              type="secondary"
              style={{ fontSize: 11, letterSpacing: '0.05em' }}
            >
              Agent 网格 · 7 个智能体协同
            </Text>
            <Paragraph
              style={{
                marginTop: 8,
                marginBottom: 0,
                fontSize: 12,
                lineHeight: 1.7,
                color: 'var(--color-mist-dark)',
              }}
            >
              <strong style={{ color: '#3B82F6' }}>评估</strong> BKT 掌握度 ·{' '}
              <strong style={{ color: '#10B981' }}>导师</strong> 苏格拉底教学 ·{' '}
              <strong style={{ color: '#F59E0B' }}>课程</strong> SM-2 路径 ·{' '}
              <strong style={{ color: '#8B5CF6' }}>提示</strong> 分级辅导 ·{' '}
              <strong style={{ color: '#F43F5E' }}>专注</strong> 状态监测 ·{' '}
              <strong style={{ color: '#1B4332' }}>评审</strong> LLM 自反思 ·{' '}
              <strong style={{ color: '#D97757' }}>辩论</strong> 多 Agent 协商
            </Paragraph>
          </Card>
        </Col>
      </Row>
    </div>
  )
}
