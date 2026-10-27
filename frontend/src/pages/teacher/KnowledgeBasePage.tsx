import { useState } from 'react'
import {
  App,
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  Modal,
  Row,
  Segmented,
  Select,
  Skeleton,
  Tag,
  Typography,
} from 'antd'
import {
  PlusOutlined,
  SearchOutlined,
  FileTextOutlined,
  DeleteOutlined,
} from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { formatDate } from '@/lib/datetime'
import { motion } from 'motion/react'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { ragApi, type DocumentListParams } from '@/lib/api/rag'
import type {
  DocumentDetailResponse,
  DocumentResponse,
  ScoredChunkResponse,
} from '@/types/api'

const { Text, Title, Paragraph } = Typography

const STATUS_COLORS: Record<string, string> = {
  indexed: '#10B981',
  ready: '#10B981',
  indexing: '#F59E0B',
  failed: '#F43F5E',
  pending: '#6B7280',
}

const STATUS_LABELS: Record<string, string> = {
  indexed: '已索引',
  ready: '就绪',
  indexing: '索引中',
  failed: '失败',
  pending: '待处理',
}

const SOURCE_LABELS: Record<string, string> = {
  text: '文本',
  markdown: 'Markdown',
  pdf: 'PDF',
  url: '网页',
}

/** 添加文档表单示例(点击整组填入,正文 ≥ 50 字以满足校验) */
const DOCUMENT_EXAMPLES: Array<{
  label: string
  title: string
  content: string
  source_type: 'text' | 'markdown'
  source_url?: string
}> = [
  {
    label: '因式分解讲义',
    title: '初中代数 · 因式分解讲义',
    source_type: 'markdown',
    content:
      '因式分解是把多项式写成几个整式乘积的形式。常用方法包括提取公因式、运用公式法、分组分解法。\n\n' +
      '提公因式: ax+ay=a(x+y)。公式法: a²-b²=(a+b)(a-b); a²±2ab+b²=(a±b)²。\n\n' +
      '分解应进行到每一个因式都不能再分解为止,并注意符号与系数的整理。',
  },
  {
    label: '二次函数要点',
    title: '二次函数图像与性质速查',
    source_type: 'text',
    content:
      '二次函数一般式 y=ax²+bx+c(a≠0)。a>0 开口向上,a<0 开口向下。对称轴为直线 x=-b/(2a)。\n' +
      '顶点坐标为(-b/(2a), (4ac-b²)/(4a))。与 x 轴交点个数由判别式 Δ=b²-4ac 决定:\n' +
      'Δ>0 两个交点,Δ=0 一个交点(顶点在 x 轴上),Δ<0 无交点。',
  },
  {
    label: '概率入门',
    title: '古典概型入门笔记',
    source_type: 'markdown',
    source_url: 'https://example.com/probability-notes',
    content:
      '古典概型要求试验的基本事件两两互斥、且每个基本事件出现的可能性相等。\n\n' +
      '事件 A 的概率 P(A)=|A|/|Ω|,其中 |Ω| 为基本事件总数,|A| 为事件 A 包含的基本事件数。\n' +
      '互斥事件可直接相加;对立事件满足 P(A)+P(Ā)=1。',
  },
]

const SEARCH_EXAMPLES = [
  '一元一次方程怎么解',
  '二次函数开口方向',
  '古典概型概率公式',
  '因式分解平方差',
]

function apiErrorDetail(err: unknown, fallback: string): string {
  return (
    (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? fallback
  )
}

export default function KnowledgeBasePage() {
  const { message, modal } = App.useApp()
  const qc = useQueryClient()
  const [tab, setTab] = useState<'documents' | 'search'>('documents')
  const [createOpen, setCreateOpen] = useState(false)
  const [viewId, setViewId] = useState<number | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [createForm] = Form.useForm<{
    title: string
    content: string
    source_type?: string
    source_url?: string
  }>()

  const params: DocumentListParams = { limit: 100 }

  const { data: docs, isLoading } = useQuery({
    queryKey: ['rag', 'documents', params],
    queryFn: () => ragApi.listDocuments(params),
  })

  const { data: viewDetail, isLoading: viewLoading } = useQuery({
    queryKey: ['rag', 'document', viewId],
    queryFn: () => ragApi.getDocument(viewId!),
    enabled: viewId != null,
  })

  const createMutation = useMutation({
    mutationFn: (v: {
      title: string
      content: string
      source_type?: string
      source_url?: string
    }) => ragApi.createDocument(v),
    onSuccess: (res) => {
      message.success(res.is_new ? '文档已入库并完成向量化' : res.message)
      setCreateOpen(false)
      createForm.resetFields()
      qc.invalidateQueries({ queryKey: ['rag', 'documents'] })
    },
    onError: (err) => message.error(apiErrorDetail(err, '添加文档失败')),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => ragApi.deleteDocument(id),
    onSuccess: () => {
      message.success('文档已删除')
      qc.invalidateQueries({ queryKey: ['rag', 'documents'] })
      if (viewId != null) setViewId(null)
    },
    onError: (err) => message.error(apiErrorDetail(err, '删除失败')),
  })

  const searchMutation = useMutation({
    mutationFn: (q: string) => ragApi.search({ query: q, top_k: 6, min_score: 0.45 }),
    onError: (err) => message.error(apiErrorDetail(err, '检索失败')),
  })

  const handleDelete = (d: DocumentResponse) => {
    modal.confirm({
      title: '确认删除文档?',
      content: `"${d.title}" 将被永久删除,相关向量也会被清除`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => deleteMutation.mutateAsync(d.id),
    })
  }

  const handleSearch = () => {
    if (!searchQuery.trim()) {
      message.warning('请输入搜索内容')
      return
    }
    searchMutation.mutate(searchQuery.trim())
  }

  return (
    <div className="max-w-7xl mx-auto">
      <PageHeader
        title="RAG 知识库"
        subtitle="粘贴文本入库 · 自动分块向量化 · 语义检索调试验证"
        extra={
          tab === 'documents' && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              添加文档
            </Button>
          )
        }
      />

      <Card bordered={false} className="lumen-card mb-4" size="small">
        <Segmented
          value={tab}
          onChange={(v) => setTab(v as 'documents' | 'search')}
          options={[
            { label: '文档列表', value: 'documents' },
            { label: '语义搜索', value: 'search' },
          ]}
        />
      </Card>

      {tab === 'documents' ? (
        isLoading ? (
          <Card bordered={false} className="lumen-card">
            <Skeleton active paragraph={{ rows: 6 }} />
          </Card>
        ) : !docs || docs.length === 0 ? (
          <EmptyState title="知识库为空" description="添加第一份文档,启用 RAG 增强生成" />
        ) : (
          <Row gutter={[16, 16]}>
            {docs.map((d, idx) => {
              const color = STATUS_COLORS[d.status] ?? '#6B7280'
              return (
                <Col key={d.id} xs={24} md={12}>
                  <motion.div
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: Math.min(idx * 0.03, 0.3) }}
                  >
                    <Card
                      bordered={false}
                      className="lumen-card lumen-card-hover"
                      onClick={() => setViewId(d.id)}
                      style={{ cursor: 'pointer' }}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex items-center gap-2 flex-1 min-w-0">
                          <FileTextOutlined style={{ color: 'var(--color-moss)', fontSize: 14 }} />
                          <Text
                            strong
                            style={{
                              fontSize: 14,
                              fontFamily: 'var(--font-serif)',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {d.title}
                          </Text>
                        </div>
                        <Tag
                          style={{
                            fontSize: 10,
                            margin: 0,
                            padding: '0 6px',
                            lineHeight: '16px',
                            background: `${color}11`,
                            border: `1px solid ${color}33`,
                            color,
                          }}
                        >
                          {STATUS_LABELS[d.status] ?? d.status}
                        </Tag>
                      </div>
                      <div className="flex items-center gap-3 mb-2">
                        <Tag
                          style={{
                            fontSize: 10,
                            margin: 0,
                            padding: '0 6px',
                            lineHeight: '16px',
                            background: 'var(--color-paper)',
                            border: '1px solid var(--color-line)',
                            color: 'var(--color-mist)',
                          }}
                        >
                          {SOURCE_LABELS[d.source_type] ?? d.source_type}
                        </Tag>
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          {d.total_chunks} 个分块
                        </Text>
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          {formatDate(d.created_at)}
                        </Text>
                      </div>
                      {d.error_message && (
                        <Paragraph
                          type="danger"
                          style={{ fontSize: 11, margin: 0, lineHeight: 1.5 }}
                          ellipsis={{ rows: 1 }}
                        >
                          {d.error_message}
                        </Paragraph>
                      )}
                      <div className="flex justify-end mt-2">
                        <Button
                          size="small"
                          type="text"
                          danger
                          icon={<DeleteOutlined />}
                          onClick={(e) => {
                            e.stopPropagation()
                            handleDelete(d)
                          }}
                          loading={deleteMutation.isPending}
                        >
                          删除
                        </Button>
                      </div>
                    </Card>
                  </motion.div>
                </Col>
              )
            })}
          </Row>
        )
      ) : (
        <Card bordered={false} className="lumen-card">
          <Title level={5} style={{ marginTop: 0 }}>
            语义检索 · 测试 RAG 召回
          </Title>
          <Text type="secondary" style={{ fontSize: 12 }}>
            输入查询,检索最相关的文档分块(余弦相似度 ≥ 0.45)
          </Text>
          <div style={{ marginTop: 8, lineHeight: 1.8 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              示例：
            </Text>
            {SEARCH_EXAMPLES.map((q) => (
              <Tag
                key={q}
                style={{
                  cursor: 'pointer',
                  marginInlineStart: 4,
                  fontSize: 12,
                  background: 'var(--color-moss-50)',
                  border: '1px solid var(--color-line)',
                  color: 'var(--color-moss)',
                }}
                onClick={() => {
                  setSearchQuery(q)
                  searchMutation.mutate(q)
                }}
              >
                {q}
              </Tag>
            ))}
          </div>
          <Input.Search
            className="mt-3"
            size="large"
            placeholder="如:一元一次方程怎么解"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onSearch={handleSearch}
            enterButton={
              <Button type="primary" icon={<SearchOutlined />} loading={searchMutation.isPending}>
                检索
              </Button>
            }
          />
          <div className="mt-4">
            {!searchMutation.data ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={searchMutation.isPending ? '检索中...' : '输入查询后显示召回结果'}
                style={{ padding: '32px 0' }}
              />
            ) : searchMutation.data.length === 0 ? (
              <EmptyState title="无匹配结果" description="尝试更换关键词或添加更多文档" />
            ) : (
              <div className="space-y-3">
                {searchMutation.data.map((chunk: ScoredChunkResponse, idx) => (
                  <motion.div
                    key={chunk.chunk_id}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: idx * 0.05 }}
                    style={{
                      padding: 14,
                      background: 'var(--color-paper)',
                      borderRadius: 8,
                      border: '1px solid var(--color-line)',
                      borderLeft: '3px solid var(--color-moss)',
                    }}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <Tag
                          style={{
                            fontSize: 10,
                            margin: 0,
                            padding: '0 6px',
                            lineHeight: '16px',
                            fontFamily: 'var(--font-mono)',
                            background: 'var(--color-moss-50)',
                            border: '1px solid var(--color-line)',
                            color: 'var(--color-moss)',
                          }}
                        >
                          #{idx + 1}
                        </Tag>
                        <Text strong style={{ fontSize: 12 }}>
                          {chunk.document_title}
                        </Text>
                        <Text type="secondary" style={{ fontSize: 10 }}>
                          chunk #{chunk.chunk_index} · {chunk.token_count} tokens
                        </Text>
                      </div>
                      <Tag
                        color="success"
                        style={{
                          fontSize: 10,
                          margin: 0,
                          padding: '0 6px',
                          lineHeight: '16px',
                          fontFamily: 'var(--font-mono)',
                        }}
                      >
                        score {chunk.score.toFixed(4)}
                      </Tag>
                    </div>
                    <Paragraph
                      style={{
                        margin: 0,
                        fontSize: 13,
                        color: 'var(--color-ink)',
                        lineHeight: 1.7,
                      }}
                    >
                      {chunk.content}
                    </Paragraph>
                  </motion.div>
                ))}
              </div>
            )}
          </div>
        </Card>
      )}

      <Modal
        open={createOpen}
        title="添加文档"
        onCancel={() => setCreateOpen(false)}
        onOk={() => createForm.submit()}
        confirmLoading={createMutation.isPending}
        okText="添加"
        cancelText="取消"
        width={680}
      >
        <Form
          form={createForm}
          layout="vertical"
          onFinish={(v) => createMutation.mutate(v)}
          className="mt-4"
          initialValues={{ source_type: 'text' }}
        >
          <Form.Item
            name="title"
            label="文档标题"
            rules={[{ required: true, message: '请输入标题' }, { max: 200 }]}
            extra={
              <div style={{ marginTop: 6, lineHeight: 1.8 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  示例：
                </Text>
                {DOCUMENT_EXAMPLES.map((ex) => (
                  <Tag
                    key={ex.label}
                    style={{
                      cursor: 'pointer',
                      marginInlineStart: 4,
                      fontSize: 12,
                      background: 'var(--color-moss-50)',
                      border: '1px solid var(--color-line)',
                      color: 'var(--color-moss)',
                    }}
                    onClick={() =>
                      createForm.setFieldsValue({
                        title: ex.title,
                        content: ex.content,
                        source_type: ex.source_type,
                        source_url: ex.source_url ?? '',
                      })
                    }
                  >
                    {ex.label}
                  </Tag>
                ))}
              </div>
            }
          >
            <Input placeholder="如:贝叶斯知识追踪原理" />
          </Form.Item>
          <Form.Item
            name="content"
            label="文档内容"
            rules={[{ required: true, message: '请输入内容' }, { min: 50, message: '至少 50 字符' }]}
            extra="当前仅支持粘贴纯文本 / Markdown,系统会自动分块并向量化"
          >
            <Input.TextArea
              rows={8}
              placeholder="粘贴文档全文,系统将自动分块并向量化"
              showCount
              maxLength={20000}
            />
          </Form.Item>
          <Row gutter={12}>
            <Col xs={24} md={12}>
              <Form.Item name="source_type" label="内容格式">
                <Select
                  options={[
                    { value: 'text', label: '文本' },
                    { value: 'markdown', label: 'Markdown' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item
                name="source_url"
                label="来源备注 URL (可选)"
                extra="仅存档引用,不会抓取网页"
              >
                <Input placeholder="https://..." />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      <Modal
        open={viewId != null}
        onCancel={() => setViewId(null)}
        title={viewDetail?.title ?? (viewLoading ? '加载中…' : '文档详情')}
        footer={
          viewDetail ? (
            <div className="flex justify-between">
              <Button
                danger
                icon={<DeleteOutlined />}
                onClick={() => handleDelete(viewDetail)}
                loading={deleteMutation.isPending}
              >
                删除
              </Button>
              <Button onClick={() => setViewId(null)}>关闭</Button>
            </div>
          ) : null
        }
        width={720}
      >
        {viewLoading ? (
          <Skeleton active paragraph={{ rows: 6 }} />
        ) : viewDetail ? (
          <DocumentDetailBody detail={viewDetail} />
        ) : (
          <Empty description="文档不存在或已删除" />
        )}
      </Modal>
    </div>
  )
}

function DocumentDetailBody({ detail }: { detail: DocumentDetailResponse }) {
  const color = STATUS_COLORS[detail.status] ?? '#6B7280'
  const chunks = detail.chunks ?? []
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <Tag
          style={{
            fontSize: 10,
            margin: 0,
            background: `${color}11`,
            border: `1px solid ${color}33`,
            color,
          }}
        >
          {STATUS_LABELS[detail.status] ?? detail.status}
        </Tag>
        <Tag style={{ fontSize: 10, margin: 0 }}>
          {SOURCE_LABELS[detail.source_type] ?? detail.source_type}
        </Tag>
        <Text type="secondary" style={{ fontSize: 11 }}>
          {detail.total_chunks} 个分块 · {formatDate(detail.created_at)}
        </Text>
      </div>
      {detail.source_url && (
        <Paragraph style={{ fontSize: 12, marginBottom: 12 }}>
          来源备注:{' '}
          <a href={detail.source_url} target="_blank" rel="noreferrer">
            {detail.source_url}
          </a>
        </Paragraph>
      )}
      {detail.error_message && (
        <Paragraph type="danger" style={{ fontSize: 12 }}>
          {detail.error_message}
        </Paragraph>
      )}
      {chunks.length === 0 ? (
        <EmptyState title="暂无分块" description="文档尚未完成索引,或内容为空" />
      ) : (
        <div className="space-y-3">
          {chunks.map((c) => (
            <div
              key={c.chunk_index}
              style={{
                padding: 12,
                background: 'var(--color-paper)',
                borderRadius: 8,
                border: '1px solid var(--color-line)',
              }}
            >
              <Text type="secondary" style={{ fontSize: 10, fontFamily: 'var(--font-mono)' }}>
                chunk #{c.chunk_index} · {c.token_count} tokens
              </Text>
              <Paragraph style={{ margin: '6px 0 0', fontSize: 13, lineHeight: 1.7 }}>
                {c.content}
              </Paragraph>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
