import { useState } from 'react'
import {
  App,
  Button,
  Card,
  Col,
  Form,
  Modal,
  Row,
  Segmented,
  Select,
  Skeleton,
  Switch,
  Tag,
  Typography,
} from 'antd'
import { ThunderboltOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { formatDateTime } from '@/lib/datetime'
import { motion } from 'motion/react'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { questionsApi, type QuestionListParams } from '@/lib/api/questions'
import { learnerApi } from '@/lib/api/learner'
import type { QuestionDetail, QuestionStatus, QuestionType } from '@/types/api'
import { parseQuestionContent, previewQuestionText } from '@/lib/questionContent'

const { Text, Paragraph } = Typography

const STATUS_META: Record<QuestionStatus, { label: string; color: string }> = {
  draft: { label: '草稿', color: '#6B7280' },
  review: { label: '审核中', color: '#F59E0B' },
  published: { label: '已发布', color: '#10B981' },
  rejected: { label: '已驳回', color: '#EF4444' },
  archived: { label: '已归档', color: '#9CA3AF' },
}

const TYPE_LABEL: Record<QuestionType, string> = {
  multiple_choice: '选择题',
  fill_blank: '填空题',
  true_false: '判断题',
  open_ended: '解答题',
}

const DELETABLE_STATUSES: QuestionStatus[] = ['draft', 'rejected', 'archived']

function apiErrorDetail(err: unknown, fallback: string): string {
  return (
    (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? fallback
  )
}

function formatAnswer(answer: QuestionDetail['answer']): string {
  if (answer == null || answer === '') return '（无参考答案）'
  if (typeof answer === 'string') return answer
  return JSON.stringify(answer, null, 2)
}

export default function QuestionsPage() {
  const { message, modal } = App.useApp()
  const qc = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<QuestionStatus | 'all'>('all')
  const [typeFilter, setTypeFilter] = useState<QuestionType | 'all'>('all')
  const [knowledgeFilter, setKnowledgeFilter] = useState<string | 'all'>('all')
  const [genOpen, setGenOpen] = useState(false)
  const [viewItem, setViewItem] = useState<QuestionDetail | null>(null)
  const [genForm] = Form.useForm<{
    knowledge_id: string
    question_type: QuestionType
    difficulty?: number
    use_rag?: boolean
  }>()

  const params: QuestionListParams = {
    status: statusFilter === 'all' ? undefined : statusFilter,
    question_type: typeFilter === 'all' ? undefined : typeFilter,
    knowledge_id: knowledgeFilter === 'all' ? undefined : knowledgeFilter,
    limit: 100,
  }

  const { data: questions, isLoading } = useQuery({
    queryKey: ['questions', 'teacher', params],
    queryFn: () => questionsApi.list(params),
  })

  const { data: graph } = useQuery({
    queryKey: ['knowledge-graph'],
    queryFn: () => learnerApi.knowledgeGraph(),
  })

  const genMutation = useMutation({
    mutationFn: (v: {
      knowledge_id: string
      question_type: QuestionType
      difficulty?: number
      use_rag?: boolean
    }) => questionsApi.generate(v),
    onSuccess: (q) => {
      if (q.is_duplicate) {
        message.info(`检测到相似题，已打开已有题目 #${q.id}`)
      } else {
        message.success(`题目 #${q.id} 已生成（草稿）`)
      }
      setGenOpen(false)
      genForm.resetFields()
      qc.invalidateQueries({ queryKey: ['questions'] })
      setViewItem(q)
    },
    onError: (err: unknown) => {
      message.error(apiErrorDetail(err, '生成失败，请检查 LLM / Embedding 配置'))
    },
  })

  const patchMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: QuestionStatus }) =>
      questionsApi.patchStatus(id, status),
    onSuccess: (q) => {
      message.success(`状态已更新为 ${STATUS_META[q.status].label}`)
      setViewItem(q)
      qc.invalidateQueries({ queryKey: ['questions'] })
    },
    onError: (err: unknown) => {
      message.error(apiErrorDetail(err, '状态更新失败'))
    },
  })

  const removeMutation = useMutation({
    mutationFn: (id: number) => questionsApi.remove(id),
    onSuccess: () => {
      message.success('题目已删除')
      qc.invalidateQueries({ queryKey: ['questions'] })
      setViewItem(null)
    },
    onError: (err: unknown) => {
      message.error(apiErrorDetail(err, '删除失败（仅草稿/已驳回/已归档可删）'))
    },
  })

  const openDetail = async (id: number) => {
    try {
      const q = await questionsApi.get(id)
      setViewItem(q)
    } catch (err: unknown) {
      message.error(apiErrorDetail(err, '加载题目失败'))
    }
  }

  const handleDelete = (q: QuestionDetail) => {
    if (!DELETABLE_STATUSES.includes(q.status)) {
      message.warning('审核中或已发布的题目请先归档/驳回后再删')
      return
    }
    modal.confirm({
      title: '确认删除题目?',
      content: `题目 #${q.id} 将被永久删除`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => removeMutation.mutateAsync(q.id),
    })
  }

  return (
    <div className="max-w-7xl mx-auto">
      <PageHeader
        title="题库管理"
        subtitle="LLM 生成 · 状态流转（草稿→审核→发布）· 难度分级 · 可选 RAG"
        extra={
          <Button type="primary" icon={<ThunderboltOutlined />} onClick={() => setGenOpen(true)}>
            LLM 生成题目
          </Button>
        }
      />

      <Card bordered={false} className="lumen-card mb-4" size="small">
        <Row gutter={[12, 12]} align="middle">
          <Col>
            <Segmented
              value={statusFilter}
              onChange={(v) => setStatusFilter(v as QuestionStatus | 'all')}
              options={[
                { label: '全部', value: 'all' },
                { label: '草稿', value: 'draft' },
                { label: '审核中', value: 'review' },
                { label: '已发布', value: 'published' },
                { label: '已驳回', value: 'rejected' },
                { label: '已归档', value: 'archived' },
              ]}
            />
          </Col>
          <Col>
            <Select
              size="middle"
              style={{ minWidth: 130 }}
              value={typeFilter}
              onChange={(v) => setTypeFilter(v)}
              options={[
                { value: 'all', label: '全部题型' },
                { value: 'multiple_choice', label: '选择题' },
                { value: 'fill_blank', label: '填空题' },
                { value: 'true_false', label: '判断题' },
                { value: 'open_ended', label: '解答题' },
              ]}
            />
          </Col>
          <Col flex="auto">
            <Select
              size="middle"
              style={{ width: '100%' }}
              value={knowledgeFilter}
              onChange={(v) => setKnowledgeFilter(v)}
              options={[
                { value: 'all', label: '全部知识点' },
                ...(graph?.nodes.map((n) => ({
                  value: n.id,
                  label: n.name,
                })) ?? []),
              ]}
              showSearch
              optionFilterProp="label"
            />
          </Col>
        </Row>
      </Card>

      {isLoading ? (
        <Row gutter={[16, 16]}>
          {[1, 2, 3, 4].map((i) => (
            <Col key={i} xs={24} md={12}>
              <Card bordered={false} className="lumen-card">
                <Skeleton active paragraph={{ rows: 3 }} />
              </Card>
            </Col>
          ))}
        </Row>
      ) : !questions || questions.length === 0 ? (
        <EmptyState title="暂无题目" description="点击右上角使用 LLM 生成题目" />
      ) : (
        <Row gutter={[16, 16]}>
          {questions.map((q, idx) => {
            const meta = STATUS_META[q.status] ?? STATUS_META.draft
            const nodeName = graph?.nodes.find((n) => n.id === q.knowledge_id)?.name ?? q.knowledge_id
            return (
              <Col key={q.id} xs={24} md={12}>
                <motion.div
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(idx * 0.02, 0.3) }}
                >
                  <Card
                    bordered={false}
                    hoverable
                    className="lumen-card lumen-card-hover"
                    onClick={() => openDetail(q.id)}
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <Tag
                          style={{
                            fontSize: 11,
                            margin: 0,
                            padding: '0 6px',
                            lineHeight: '18px',
                            fontFamily: 'var(--font-mono)',
                            background: 'var(--color-moss-50)',
                            border: '1px solid var(--color-line)',
                            color: 'var(--color-moss)',
                          }}
                        >
                          #{q.id}
                        </Tag>
                        <Tag
                          style={{
                            fontSize: 11,
                            margin: 0,
                            padding: '0 6px',
                            lineHeight: '18px',
                            background: 'transparent',
                            border: '1px solid var(--color-line)',
                            color: 'var(--color-mist)',
                          }}
                        >
                          {TYPE_LABEL[q.question_type]}
                        </Tag>
                        <Tag
                          style={{
                            fontSize: 11,
                            margin: 0,
                            padding: '0 6px',
                            lineHeight: '18px',
                            background: `${meta.color}11`,
                            border: `1px solid ${meta.color}33`,
                            color: meta.color,
                          }}
                        >
                          {meta.label}
                        </Tag>
                      </div>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        难度 {q.difficulty}
                      </Text>
                    </div>
                    <Paragraph
                      style={{
                        fontSize: 13,
                        color: 'var(--color-ink)',
                        marginBottom: 8,
                        lineHeight: 1.6,
                      }}
                      ellipsis={{ rows: 2 }}
                    >
                      {previewQuestionText(q.content) || '点击查看题目详情'}
                    </Paragraph>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {nodeName} · {formatDateTime(q.created_at, 'MM-DD HH:mm')}
                    </Text>
                  </Card>
                </motion.div>
              </Col>
            )
          })}
        </Row>
      )}

      <Modal
        open={genOpen}
        title="LLM 生成题目"
        onCancel={() => setGenOpen(false)}
        onOk={() => genForm.submit()}
        confirmLoading={genMutation.isPending}
        okText="生成"
        cancelText="取消"
      >
        <Form
          form={genForm}
          layout="vertical"
          onFinish={(v) => genMutation.mutate(v)}
          className="mt-4"
          initialValues={{ difficulty: 3, use_rag: false, question_type: 'multiple_choice' }}
        >
          <Form.Item
            name="knowledge_id"
            label="知识点"
            rules={[{ required: true, message: '请选择知识点' }]}
          >
            <Select
              placeholder="选择知识点"
              showSearch
              optionFilterProp="label"
              options={(graph?.nodes ?? []).map((n) => ({
                value: n.id,
                label: n.name,
              }))}
            />
          </Form.Item>
          <Row gutter={12}>
            <Col xs={24} md={12}>
              <Form.Item
                name="question_type"
                label="题型"
                rules={[{ required: true, message: '请选择题型' }]}
              >
                <Select
                  placeholder="选择题型"
                  options={[
                    { value: 'multiple_choice', label: '选择题' },
                    { value: 'fill_blank', label: '填空题' },
                    { value: 'true_false', label: '判断题' },
                    { value: 'open_ended', label: '解答题' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="difficulty" label="难度 (1-5)">
                <Select
                  options={[1, 2, 3, 4, 5].map((d) => ({
                    value: d,
                    label: `${d} ${'★'.repeat(d)}`,
                  }))}
                />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="use_rag" label="启用 RAG 增强" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Text type="secondary" style={{ fontSize: 11 }}>
            需知识库中已有可检索文档；检索失败时仍会出题，但不保证贴合教材。依赖外部 LLM /
            Embedding，配置异常时会提示失败。
          </Text>
        </Form>
      </Modal>

      <Modal
        open={!!viewItem}
        onCancel={() => setViewItem(null)}
        title={
          viewItem && (
            <div className="flex items-center gap-2">
              <Text strong>题目 #{viewItem.id}</Text>
              <Tag style={{ fontSize: 11, margin: 0 }}>{TYPE_LABEL[viewItem.question_type]}</Tag>
              <Tag
                style={{
                  fontSize: 11,
                  margin: 0,
                  background: `${STATUS_META[viewItem.status]?.color ?? '#6B7280'}11`,
                  border: `1px solid ${STATUS_META[viewItem.status]?.color ?? '#6B7280'}33`,
                  color: STATUS_META[viewItem.status]?.color ?? '#6B7280',
                }}
              >
                {STATUS_META[viewItem.status]?.label ?? viewItem.status}
              </Tag>
            </div>
          )
        }
        footer={
          viewItem && (
            <div className="flex justify-between flex-wrap gap-2">
              {DELETABLE_STATUSES.includes(viewItem.status) ? (
                <Button danger onClick={() => handleDelete(viewItem)}>
                  删除
                </Button>
              ) : (
                <Text type="secondary" style={{ fontSize: 12, alignSelf: 'center' }}>
                  审核中/已发布不可直接删除
                </Text>
              )}
              <div className="flex gap-2 flex-wrap">
                <Button onClick={() => setViewItem(null)}>关闭</Button>
                {viewItem.status === 'draft' && (
                  <Button
                    type="primary"
                    onClick={() => patchMutation.mutate({ id: viewItem.id, status: 'review' })}
                    loading={patchMutation.isPending}
                  >
                    提交审核
                  </Button>
                )}
                {viewItem.status === 'review' && (
                  <>
                    <Button
                      danger
                      onClick={() => patchMutation.mutate({ id: viewItem.id, status: 'rejected' })}
                      loading={patchMutation.isPending}
                    >
                      驳回
                    </Button>
                    <Button
                      type="primary"
                      onClick={() => patchMutation.mutate({ id: viewItem.id, status: 'published' })}
                      loading={patchMutation.isPending}
                    >
                      通过并发布
                    </Button>
                  </>
                )}
                {viewItem.status === 'rejected' && (
                  <Button
                    onClick={() => patchMutation.mutate({ id: viewItem.id, status: 'draft' })}
                    loading={patchMutation.isPending}
                  >
                    回退为草稿
                  </Button>
                )}
                {viewItem.status === 'published' && (
                  <Button
                    onClick={() => patchMutation.mutate({ id: viewItem.id, status: 'archived' })}
                    loading={patchMutation.isPending}
                  >
                    归档
                  </Button>
                )}
                {viewItem.status === 'archived' && (
                  <Button
                    onClick={() => patchMutation.mutate({ id: viewItem.id, status: 'draft' })}
                    loading={patchMutation.isPending}
                  >
                    恢复为草稿
                  </Button>
                )}
              </div>
            </div>
          )
        }
        width={680}
      >
        {viewItem && (
          <div>
            <div className="mb-3">
              <Text type="secondary" style={{ fontSize: 11, letterSpacing: '0.05em' }}>
                题目内容
              </Text>
              {(() => {
                const parsed = parseQuestionContent(viewItem.content)
                return (
                  <div
                    style={{
                      padding: 16,
                      background: 'var(--color-paper)',
                      borderRadius: 8,
                      fontSize: 14,
                      lineHeight: 1.7,
                      marginTop: 4,
                    }}
                  >
                    <Paragraph style={{ marginBottom: parsed.options.length ? 12 : 0 }}>
                      {parsed.stem || '（题目正文缺失）'}
                    </Paragraph>
                    {parsed.options.length > 0 && (
                      <ul style={{ margin: 0, paddingLeft: 20 }}>
                        {parsed.options.map((opt) => (
                          <li key={opt.key} style={{ marginBottom: 4 }}>
                            <strong>{opt.key}.</strong> {opt.text}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )
              })()}
            </div>
            <div className="mb-3">
              <Text type="secondary" style={{ fontSize: 11, letterSpacing: '0.05em' }}>
                参考答案
              </Text>
              <Paragraph
                style={{
                  padding: 16,
                  background: 'rgba(27, 67, 50, 0.04)',
                  borderRadius: 8,
                  fontSize: 13,
                  lineHeight: 1.7,
                  marginTop: 4,
                  border: '1px solid var(--color-line)',
                  whiteSpace: 'pre-wrap',
                }}
              >
                {formatAnswer(viewItem.answer)}
              </Paragraph>
            </div>
            {viewItem.analysis && (
              <div>
                <Text type="secondary" style={{ fontSize: 11, letterSpacing: '0.05em' }}>
                  解析
                </Text>
                <Paragraph
                  style={{
                    padding: 16,
                    background: 'var(--color-paper)',
                    borderRadius: 8,
                    fontSize: 13,
                    lineHeight: 1.7,
                    marginTop: 4,
                  }}
                >
                  {viewItem.analysis}
                </Paragraph>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
