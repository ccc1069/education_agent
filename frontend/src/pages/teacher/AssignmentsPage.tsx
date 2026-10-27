import { useState } from 'react'
import {
  App,
  Button,
  Card,
  Col,
  DatePicker,
  Form,
  Input,
  Modal,
  Row,
  Segmented,
  Select,
  Skeleton,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { formatDateTime } from '@/lib/datetime'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { teacherApi } from '@/lib/api/teacher'
import { questionsApi } from '@/lib/api/questions'
import { learnerApi } from '@/lib/api/learner'
import type { AssignmentSummary, QuestionSummary } from '@/types/api'

const { Text, Paragraph } = Typography

const STATUS_META: Record<AssignmentSummary['status'], { label: string; color: string }> = {
  draft: { label: '草稿', color: '#6B7280' },
  published: { label: '已发布', color: '#10B981' },
  closed: { label: '已关闭', color: '#F59E0B' },
  archived: { label: '已归档', color: '#9CA3AF' },
}

type StatusFilter = 'all' | AssignmentSummary['status']

type FormValues = {
  title: string
  class_id: number
  question_ids: number[]
  description?: string
  due_at?: dayjs.Dayjs | null
}

const TITLE_EXAMPLES = [
  '第3周 · 方程与函数巩固练',
  '几何冲刺 · 勾股定理应用',
  '入学摸底 · 基础运算',
] as const

const DESC_EXAMPLES = [
  '覆盖一元一次方程与二次函数入门，完成后对照错题订正。'
] as const

function apiErrorDetail(err: unknown, fallback: string): string {
  return (
    (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? fallback
  )
}

export default function AssignmentsPage() {
  const { message, modal } = App.useApp()
  const qc = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<AssignmentSummary | null>(null)
  const [form] = Form.useForm<FormValues>()

  const isEdit = editing != null
  const editLockedClass = isEdit && editing.status !== 'draft'
  const requireQuestions = !isEdit || editing.status !== 'draft'

  const { data: assignments, isLoading } = useQuery({
    queryKey: ['teacher', 'assignments', statusFilter],
    queryFn: () =>
      teacherApi.listAssignments({
        status: statusFilter === 'all' ? undefined : statusFilter,
      }),
  })

  const { data: classes } = useQuery({
    queryKey: ['teacher', 'classes'],
    queryFn: () => teacherApi.listClasses(),
  })

  const activeClasses = (classes ?? []).filter((c) => c.is_active)
  const classOptions = (() => {
    const opts = activeClasses.map((c) => ({
      value: c.id,
      label: `${c.name} (${c.member_count} 人)`,
    }))
    if (editing) {
      const cur = classes?.find((c) => c.id === editing.class_id)
      if (cur && !opts.some((o) => o.value === cur.id)) {
        opts.unshift({
          value: cur.id,
          label: `${cur.name}${cur.is_active ? '' : '（已归档）'}`,
        })
      }
    }
    return opts
  })()

  const { data: questions } = useQuery({
    queryKey: ['questions', 'teacher-list', { status: 'published', limit: 200 }],
    queryFn: () => questionsApi.list({ status: 'published', limit: 200 }),
  })

  const { data: graph } = useQuery({
    queryKey: ['knowledge-graph'],
    queryFn: () => learnerApi.knowledgeGraph(),
  })

  const closeForm = () => {
    setFormOpen(false)
    setEditing(null)
    form.resetFields()
  }

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    setFormOpen(true)
  }

  const openEdit = (a: AssignmentSummary) => {
    if (a.status === 'archived') {
      message.warning('已归档作业不可编辑')
      return
    }
    setEditing(a)
    form.setFieldsValue({
      title: a.title,
      class_id: a.class_id,
      question_ids: a.question_ids ?? [],
      description: a.description ?? undefined,
      due_at: a.due_at ? dayjs(a.due_at) : null,
    })
    setFormOpen(true)
  }

  const createMutation = useMutation({
    mutationFn: (v: FormValues) =>
      teacherApi.createAssignment({
        title: v.title,
        class_id: v.class_id,
        question_ids: v.question_ids,
        description: v.description,
        due_at: v.due_at?.toISOString(),
      }),
    onSuccess: () => {
      message.success('作业已创建（草稿）')
      closeForm()
      qc.invalidateQueries({ queryKey: ['teacher', 'assignments'] })
    },
    onError: (err: unknown) => {
      message.error(apiErrorDetail(err, '创建失败'))
    },
  })

  const updateMutation = useMutation({
    mutationFn: (v: FormValues) =>
      teacherApi.updateAssignment(editing!.id, {
        title: v.title,
        class_id: editing!.status === 'draft' ? v.class_id : undefined,
        question_ids: v.question_ids ?? [],
        description: v.description ?? '',
        due_at: v.due_at ? v.due_at.toISOString() : null,
      }),
    onSuccess: () => {
      message.success('作业已保存')
      closeForm()
      qc.invalidateQueries({ queryKey: ['teacher', 'assignments'] })
    },
    onError: (err: unknown) => {
      message.error(apiErrorDetail(err, '保存失败'))
    },
  })

  const patchMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: 'published' | 'closed' | 'archived' }) =>
      teacherApi.patchAssignmentStatus(id, status),
    onSuccess: () => {
      message.success('状态已更新')
      qc.invalidateQueries({ queryKey: ['teacher', 'assignments'] })
    },
    onError: (err: unknown) => {
      message.error(apiErrorDetail(err, '状态更新失败'))
    },
  })

  const removeMutation = useMutation({
    mutationFn: (id: number) => teacherApi.removeAssignment(id),
    onSuccess: () => {
      message.success('草稿已删除')
      qc.invalidateQueries({ queryKey: ['teacher', 'assignments'] })
    },
    onError: (err: unknown) => {
      message.error(apiErrorDetail(err, '删除失败（仅草稿可删，其它状态请归档）'))
    },
  })

  const handleAction = (a: AssignmentSummary, action: 'publish' | 'close' | 'archive' | 'delete') => {
    if (action === 'delete') {
      if (a.status !== 'draft') {
        message.warning('仅草稿可删除，已发布/关闭的作业请归档')
        return
      }
      modal.confirm({
        title: '确认删除草稿?',
        content: `草稿「${a.title}」将被永久删除`,
        okText: '删除',
        okButtonProps: { danger: true },
        cancelText: '取消',
        onOk: () => removeMutation.mutateAsync(a.id),
      })
      return
    }
    if (action === 'publish' && !(a.question_ids?.length > 0)) {
      message.warning('请先补充题目后再发布')
      return
    }
    const target = action === 'publish' ? 'published' : action === 'close' ? 'closed' : 'archived'
    patchMutation.mutate({ id: a.id, status: target })
  }

  const saving = createMutation.isPending || updateMutation.isPending

  return (
    <div className="max-w-7xl mx-auto">
      <PageHeader
        title="作业管理"
        subtitle="按班级布置题目，管理草稿 / 发布 / 关闭 / 归档；草稿与已发布作业可编辑"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            布置作业
          </Button>
        }
      />

      <Card bordered={false} className="lumen-card mb-4" size="small">
        <Segmented
          value={statusFilter}
          onChange={(v) => setStatusFilter(v as StatusFilter)}
          options={[
            { label: '全部', value: 'all' },
            { label: '草稿', value: 'draft' },
            { label: '已发布', value: 'published' },
            { label: '已关闭', value: 'closed' },
            { label: '已归档', value: 'archived' },
          ]}
        />
      </Card>

      {isLoading ? (
        <Card bordered={false} className="lumen-card">
          <Skeleton active paragraph={{ rows: 6 }} />
        </Card>
      ) : !assignments || assignments.length === 0 ? (
        <EmptyState title="暂无作业" description="点击右上角布置作业,选择题目和班级" />
      ) : (
        <Card bordered={false} className="lumen-card">
          <Table
            dataSource={assignments}
            rowKey="id"
            pagination={{ pageSize: 15, showSizeChanger: false }}
            columns={[
              {
                title: '作业',
                dataIndex: 'title',
                key: 'title',
                render: (title: string, r: AssignmentSummary) => (
                  <div>
                    <Text strong style={{ fontSize: 13, fontFamily: 'var(--font-serif)' }}>
                      {title}
                    </Text>
                    {r.description && (
                      <Paragraph
                        type="secondary"
                        style={{ fontSize: 11, margin: 0, lineHeight: 1.5 }}
                        ellipsis={{ rows: 1 }}
                      >
                        {r.description}
                      </Paragraph>
                    )}
                  </div>
                ),
              },
              {
                title: '班级',
                dataIndex: 'class_id',
                key: 'class_id',
                width: 100,
                render: (cid: number) => {
                  const cls = classes?.find((c) => c.id === cid)
                  return (
                    <Tag
                      style={{
                        fontSize: 11,
                        margin: 0,
                        background: 'var(--color-moss-50)',
                        border: '1px solid var(--color-line)',
                        color: 'var(--color-moss)',
                      }}
                    >
                      {cls?.name ?? `#${cid}`}
                    </Tag>
                  )
                },
              },
              {
                title: '题目数',
                dataIndex: 'question_ids',
                key: 'count',
                width: 110,
                render: (ids: number[]) =>
                  ids.length === 0 ? (
                    <Tag
                      style={{
                        fontSize: 11,
                        margin: 0,
                        background: '#FEF3C7',
                        border: '1px solid #F59E0B44',
                        color: '#B45309',
                      }}
                    >
                      题目待补充
                    </Tag>
                  ) : (
                    <Text style={{ fontSize: 13, fontFamily: 'var(--font-mono)' }}>{ids.length}</Text>
                  ),
              },
              {
                title: '状态',
                dataIndex: 'status',
                key: 'status',
                width: 100,
                render: (s: AssignmentSummary['status']) => {
                  const meta = STATUS_META[s]
                  return (
                    <Tag
                      style={{
                        fontSize: 11,
                        margin: 0,
                        background: `${meta.color}11`,
                        border: `1px solid ${meta.color}33`,
                        color: meta.color,
                      }}
                    >
                      {meta.label}
                    </Tag>
                  )
                },
              },
              {
                title: '截止时间',
                dataIndex: 'due_at',
                key: 'due_at',
                width: 160,
                render: (due: string | null) =>
                  due ? (
                    <Text style={{ fontSize: 12 }}>{formatDateTime(due, 'YYYY-MM-DD HH:mm')}</Text>
                  ) : (
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      无
                    </Text>
                  ),
              },
              {
                title: '操作',
                key: 'action',
                width: 220,
                render: (_: unknown, a: AssignmentSummary) => {
                  const emptyQs = !(a.question_ids?.length > 0)
                  return (
                    <div className="flex gap-1 flex-wrap">
                      {a.status !== 'archived' && (
                        <Button size="small" type="link" onClick={() => openEdit(a)}>
                          编辑
                        </Button>
                      )}
                      {a.status === 'draft' && (
                        <Tooltip title={emptyQs ? '请先补充题目后再发布' : undefined}>
                          <Button
                            size="small"
                            type="link"
                            disabled={emptyQs || patchMutation.isPending}
                            onClick={() => handleAction(a, 'publish')}
                          >
                            发布
                          </Button>
                        </Tooltip>
                      )}
                      {a.status === 'published' && (
                        <Button size="small" type="link" onClick={() => handleAction(a, 'close')}>
                          关闭
                        </Button>
                      )}
                      {a.status !== 'archived' && (
                        <Button size="small" type="link" onClick={() => handleAction(a, 'archive')}>
                          归档
                        </Button>
                      )}
                      {a.status === 'draft' && (
                        <Button
                          size="small"
                          type="link"
                          danger
                          onClick={() => handleAction(a, 'delete')}
                        >
                          删除
                        </Button>
                      )}
                    </div>
                  )
                },
              },
            ]}
          />
        </Card>
      )}

      <Modal
        open={formOpen}
        title={isEdit ? '编辑作业' : '布置作业'}
        onCancel={closeForm}
        onOk={() => form.submit()}
        confirmLoading={saving}
        okText={isEdit ? '保存' : '创建草稿'}
        cancelText="取消"
        width={680}
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(v) => (isEdit ? updateMutation.mutate(v) : createMutation.mutate(v))}
          className="mt-4"
        >
          <Form.Item
            name="title"
            label="作业标题"
            rules={[{ required: true, message: '请输入标题' }, { max: 100 }]}
            extra={
              !isEdit ? (
                <div style={{ marginTop: 6, lineHeight: 1.8 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    示例：
                  </Text>
                  {TITLE_EXAMPLES.map((t) => (
                    <Tag
                      key={t}
                      style={{
                        cursor: 'pointer',
                        marginInlineStart: 4,
                        fontSize: 12,
                        background: 'var(--color-moss-50)',
                        border: '1px solid var(--color-line)',
                        color: 'var(--color-moss)',
                      }}
                      onClick={() => form.setFieldValue('title', t)}
                    >
                      {t}
                    </Tag>
                  ))}
                </div>
              ) : undefined
            }
          >
            <Input placeholder="输入作业标题" />
          </Form.Item>
          <Row gutter={12}>
            <Col xs={24} md={12}>
              <Form.Item
                name="class_id"
                label="班级"
                rules={[{ required: true, message: '请选择班级' }]}
                extra={editLockedClass ? '已发布后不可换班' : undefined}
              >
                <Select
                  placeholder="选择进行中的班级"
                  disabled={editLockedClass}
                  options={classOptions}
                  notFoundContent={!classOptions.length ? '暂无进行中的班级（已归档班不可布置）' : undefined}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="due_at" label="截止时间">
                <DatePicker
                  showTime
                  allowClear
                  format="YYYY-MM-DD HH:mm"
                  style={{ width: '100%' }}
                  placeholder="请选择截止时间"
                  disabledDate={(d) => d.isBefore(dayjs().startOf('day'))}
                />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item
            name="description"
            label="作业说明"
            rules={[{ max: 500 }]}
            extra={
              !isEdit ? (
                <div style={{ marginTop: 6, lineHeight: 1.8 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    示例：
                  </Text>
                  {DESC_EXAMPLES.map((d) => (
                    <Tag
                      key={d}
                      style={{
                        cursor: 'pointer',
                        marginInlineStart: 4,
                        fontSize: 12,
                        maxWidth: '100%',
                        whiteSpace: 'normal',
                        height: 'auto',
                        background: 'var(--color-moss-50)',
                        border: '1px solid var(--color-line)',
                        color: 'var(--color-moss)',
                      }}
                      onClick={() => form.setFieldValue('description', d)}
                    >
                      {d.length > 28 ? `${d.slice(0, 28)}…` : d}
                    </Tag>
                  ))}
                </div>
              ) : undefined
            }
          >
            <Input.TextArea rows={2} placeholder="可选" maxLength={500} showCount />
          </Form.Item>
          <Form.Item
            name="question_ids"
            label="选择题目"
            rules={
              requireQuestions
                ? [{ required: true, message: '至少选择一道题目', type: 'array', min: 1 }]
                : []
            }
            extra={
              isEdit && editing.status === 'draft'
                ? '草稿可先不选题，保存后标为「题目待补充」'
                : undefined
            }
          >
            <Select
              mode="multiple"
              placeholder="从已发布题库中选择"
              optionFilterProp="label"
              options={(questions ?? []).map((q: QuestionSummary) => {
                const nodeName =
                  graph?.nodes.find((n) => n.id === q.knowledge_id)?.name ?? q.knowledge_id
                return {
                  value: q.id,
                  label: `#${q.id} · ${nodeName} · 难度 ${q.difficulty}`,
                }
              })}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
