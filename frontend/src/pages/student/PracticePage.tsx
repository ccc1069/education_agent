import { useMemo, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Input,
  Modal,
  Row,
  Segmented,
  Select,
  Skeleton,
  Tag,
  Typography,
} from 'antd'
import { CheckCircleTwoTone, CloseCircleTwoTone } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { questionsApi, type QuestionListParams } from '@/lib/api/questions'
import { learnerApi } from '@/lib/api/learner'
import { knowledgeName } from '@/lib/knowledgeLabel'
import { parseQuestionContent, previewQuestionText } from '@/lib/questionContent'
import type { QuestionDetail, QuestionStatus, QuestionType } from '@/types/api'

const { Text, Paragraph } = Typography

const STATUS_OPTIONS: { label: string; value: QuestionStatus | 'all' }[] = [
  { label: '全部', value: 'all' },
  { label: '已发布', value: 'published' },
  { label: '草稿', value: 'draft' },
  { label: '审核中', value: 'review' },
]

const TYPE_LABEL: Record<QuestionType, string> = {
  multiple_choice: '选择题',
  fill_blank: '填空题',
  true_false: '判断题',
  open_ended: '解答题',
}

export default function PracticePage() {
  const { message } = App.useApp()
  const qc = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<QuestionStatus | 'all'>('published')
  const [typeFilter, setTypeFilter] = useState<QuestionType | 'all'>('all')
  const [selected, setSelected] = useState<QuestionDetail | null>(null)
  const [answer, setAnswer] = useState('')
  const [checkResult, setCheckResult] = useState<{ is_correct: boolean; feedback: string } | null>(
    null,
  )

  const params: QuestionListParams = {
    status: statusFilter === 'all' ? undefined : statusFilter,
    question_type: typeFilter === 'all' ? undefined : typeFilter,
    limit: 50,
  }

  const { data: questions, isLoading } = useQuery({
    queryKey: ['questions', 'practice', params],
    queryFn: () => questionsApi.list(params),
  })

  const { data: graph } = useQuery({
    queryKey: ['knowledge-graph'],
    queryFn: () => learnerApi.knowledgeGraph(),
  })

  const selectedParsed = useMemo(
    () => (selected ? parseQuestionContent(selected.content) : null),
    [selected],
  )

  const checkMutation = useMutation({
    mutationFn: ({ id, ans }: { id: number; ans: unknown }) =>
      questionsApi.check(id, { student_answer: ans }),
    onSuccess: (res) => {
      setCheckResult({ is_correct: res.is_correct, feedback: res.feedback })
      qc.invalidateQueries({ queryKey: ['progress'] })
    },
  })

  const handleOpen = async (id: number) => {
    const detail = await questionsApi.get(id)
    setSelected(detail)
    setAnswer('')
    setCheckResult(null)
  }

  const handleSubmit = () => {
    if (!selected) return
    if (!answer.trim()) {
      message.warning('请先作答')
      return
    }
    checkMutation.mutate({ id: selected.id, ans: answer.trim() })
  }

  return (
    <div className="max-w-6xl mx-auto">
      <PageHeader
        title="练习题库"
        subtitle="按知识点和题型筛选题目,作答后即时获得反馈"
        extra={
          <Segmented
            options={STATUS_OPTIONS}
            value={statusFilter}
            onChange={(v) => setStatusFilter(v as QuestionStatus | 'all')}
          />
        }
      />

      <Card bordered={false} className="lumen-card mb-4" size="small">
        <Row gutter={[12, 12]} align="middle">
          <Col>
            <Text type="secondary" style={{ fontSize: 12 }}>
              题型
            </Text>
          </Col>
          <Col flex="auto">
            <Select
              size="small"
              style={{ minWidth: 160 }}
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
        <EmptyState title="暂无题目" description="尝试调整筛选条件,或联系教师生成题目" />
      ) : (
        <Row gutter={[16, 16]}>
          {questions.map((q) => {
            return (
              <Col key={q.id} xs={24} md={12}>
                <Card
                  bordered={false}
                  hoverable
                  className="lumen-card lumen-card-hover"
                  onClick={() => handleOpen(q.id)}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Tag
                        style={{
                          fontSize: 11,
                          margin: 0,
                          padding: '0 6px',
                          lineHeight: '18px',
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
                    </div>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      难度 {q.difficulty}
                    </Text>
                  </div>
                  <Text
                    style={{
                      fontSize: 13,
                      color: 'var(--color-ink)',
                      display: 'block',
                      marginBottom: 8,
                    }}
                  >
                    {previewQuestionText(q.content) || '点击查看题目详情'}
                  </Text>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {knowledgeName(graph?.nodes, q.knowledge_id)}
                  </Text>
                </Card>
              </Col>
            )
          })}
        </Row>
      )}

      <Modal
        open={!!selected}
        onCancel={() => setSelected(null)}
        title={
          selected && (
            <div className="flex items-center gap-2">
              <Text strong>题目 #{selected.id}</Text>
              <Tag color="default" style={{ fontSize: 11 }}>
                {knowledgeName(graph?.nodes, selected.knowledge_id)}
              </Tag>
            </div>
          )
        }
        footer={
          selected && (
            <div className="flex justify-between">
              <Button onClick={() => setSelected(null)}>关闭</Button>
              <Button type="primary" loading={checkMutation.isPending} onClick={handleSubmit}>
                提交答案
              </Button>
            </div>
          )
        }
        width={640}
      >
        {selected && selectedParsed && (
          <div>
            <div
              style={{
                padding: 16,
                background: 'var(--color-paper)',
                borderRadius: 8,
                fontSize: 14,
                lineHeight: 1.7,
                marginBottom: 12,
              }}
            >
              <Paragraph style={{ marginBottom: selectedParsed.options.length ? 12 : 0 }}>
                {selectedParsed.stem || '（题目正文缺失）'}
              </Paragraph>
              {selectedParsed.options.length > 0 && (
                <ul style={{ margin: 0, paddingLeft: 20 }}>
                  {selectedParsed.options.map((opt) => (
                    <li key={opt.key} style={{ marginBottom: 4 }}>
                      <strong>{opt.key}.</strong> {opt.text}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <Text type="secondary" style={{ fontSize: 12 }}>
              你的答案
            </Text>

            {selected.question_type === 'multiple_choice' &&
            selectedParsed.options.length > 0 ? (
              <div className="mt-1 flex flex-col gap-2">
                {selectedParsed.options.map((opt) => {
                  const selectedOpt = answer === opt.key || answer === opt.text
                  return (
                    <Button
                      key={opt.key}
                      type={selectedOpt ? 'primary' : 'default'}
                      block
                      style={{ textAlign: 'left', height: 'auto', padding: '8px 12px' }}
                      onClick={() => setAnswer(opt.key)}
                    >
                      <strong>{opt.key}.</strong> {opt.text}
                    </Button>
                  )
                })}
              </div>
            ) : selected.question_type === 'true_false' ? (
              <div className="mt-1 flex gap-2">
                {['true', 'false'].map((v) => (
                  <Button
                    key={v}
                    type={answer === v ? 'primary' : 'default'}
                    onClick={() => setAnswer(v)}
                  >
                    {v === 'true' ? '正确' : '错误'}
                  </Button>
                ))}
              </div>
            ) : (
              <Input.TextArea
                className="mt-1"
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                placeholder="输入你的答案..."
                autoSize={{ minRows: 3, maxRows: 6 }}
              />
            )}

            {checkResult && (
              <Alert
                className="mt-3"
                type={checkResult.is_correct ? 'success' : 'warning'}
                showIcon
                icon={
                  checkResult.is_correct ? (
                    <CheckCircleTwoTone twoToneColor="#10B981" />
                  ) : (
                    <CloseCircleTwoTone twoToneColor="#F59E0B" />
                  )
                }
                message={checkResult.is_correct ? '回答正确!' : '还需完善'}
                description={checkResult.feedback}
              />
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
