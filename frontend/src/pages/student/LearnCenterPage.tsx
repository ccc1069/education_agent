import { useState } from 'react'
import { App, Button, Card, Col, Empty, Form, Input, Modal, Row, Skeleton, Tag, Typography } from 'antd'
import { UsergroupAddOutlined } from '@ant-design/icons'
import { Link } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { motion } from 'motion/react'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { MasteryBar } from '@/components/learner/MasteryBar'
import { learnerApi } from '@/lib/api/learner'
import { teacherApi } from '@/lib/api/teacher'
import { knowledgeNames } from '@/lib/knowledgeLabel'
import { useAuthStore } from '@/lib/store/authStore'

const { Text, Title, Paragraph } = Typography

export default function LearnCenterPage() {
  const { message } = App.useApp()
  const user = useAuthStore((s) => s.user)
  const [joinOpen, setJoinOpen] = useState(false)
  const [joinForm] = Form.useForm<{ invite_code: string }>()

  const { data: graphData, isLoading: graphLoading } = useQuery({
    queryKey: ['knowledge-graph'],
    queryFn: () => learnerApi.knowledgeGraph(),
  })

  const { data: progressData, isLoading: progressLoading } = useQuery({
    queryKey: ['progress', user?.learner_id],
    queryFn: () => learnerApi.progress(user!.learner_id!),
    enabled: !!user?.learner_id,
  })

  const joinMutation = useMutation({
    mutationFn: (code: string) => teacherApi.joinClass(code.trim().toUpperCase()),
    onSuccess: (res) => {
      const name = res.name ? `「${res.name}」` : `（ID ${res.class_id}）`
      if (res.already_member) {
        message.info(`你已在班级 ${name} 中`)
      } else {
        message.success(`已加入班级 ${name}`)
      }
      setJoinOpen(false)
      joinForm.resetFields()
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        '加入失败，请检查邀请码'
      message.error(detail)
    },
  })

  const nodes = graphData?.nodes ?? []
  const learningOrder = graphData?.learning_order ?? []
  const progress = progressData?.status === 'no_data' ? {} : progressData?.progress ?? {}
  const weakPoints = progressData?.status === 'no_data' ? [] : progressData?.weak_points ?? []
  const strongPoints = progressData?.status === 'no_data' ? [] : progressData?.strong_points ?? []

  const totalMastered = strongPoints.length
  const avgMastery =
    nodes.length > 0
      ? nodes.reduce((acc, n) => acc + (progress[n.id] ?? 0), 0) / nodes.length
      : 0

  return (
    <div className="max-w-6xl mx-auto">
      <PageHeader
        title="学习中心"
        subtitle="选择一个知识点开始学习,系统会根据你的掌握度推荐合适的起点"
        loading={graphLoading && !graphData}
        extra={
          <div className="flex gap-3 items-start flex-wrap">
            {user?.role === 'student' && (
              <Button icon={<UsergroupAddOutlined />} onClick={() => setJoinOpen(true)}>
                加入班级
              </Button>
            )}
            <Card size="small" bordered={false} className="lumen-card" style={{ minWidth: 100 }}>
              <Text type="secondary" style={{ fontSize: 11, letterSpacing: '0.05em' }}>
                知识点
              </Text>
              <div
                className="lumen-mono"
                style={{ fontSize: 20, fontWeight: 600, color: 'var(--color-moss)' }}
              >
                {nodes.length}
              </div>
            </Card>
            <Card size="small" bordered={false} className="lumen-card" style={{ minWidth: 100 }}>
              <Text type="secondary" style={{ fontSize: 11, letterSpacing: '0.05em' }}>
                平均掌握
              </Text>
              <div
                className="lumen-mono"
                style={{ fontSize: 20, fontWeight: 600, color: 'var(--color-sienna)' }}
              >
                {(avgMastery * 100).toFixed(0)}%
              </div>
            </Card>
            <Card size="small" bordered={false} className="lumen-card" style={{ minWidth: 100 }}>
              <Text type="secondary" style={{ fontSize: 11, letterSpacing: '0.05em' }}>
                已掌握
              </Text>
              <div
                className="lumen-mono"
                style={{ fontSize: 20, fontWeight: 600, color: '#10B981' }}
              >
                {totalMastered}
              </div>
            </Card>
          </div>
        }
      />

      {weakPoints.length > 0 && (
        <Card
          bordered={false}
          className="lumen-card mb-6"
          style={{
            background:
              'linear-gradient(135deg, rgba(244, 63, 94, 0.04) 0%, rgba(217, 119, 87, 0.04) 100%)',
          }}
        >
          <div className="flex items-start gap-3">
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: 8,
                background: 'rgba(244, 63, 94, 0.12)',
                color: '#F43F5E',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontFamily: 'var(--font-serif)',
                fontWeight: 700,
                flexShrink: 0,
              }}
            >
              !
            </div>
            <div className="flex-1">
              <Title level={5} style={{ margin: '0 0 4px' }}>
                需要重点关注的 {weakPoints.length} 个知识点
              </Title>
              <div className="flex flex-wrap gap-2">
                {weakPoints.map((p) => {
                  const node = nodes.find((n) => n.id === p.id)
                  return (
                    <Link key={p.id} to={`/learn/${p.id}`}>
                      <Tag
                        style={{
                          background: 'var(--color-card)',
                          border: '1px solid rgba(244, 63, 94, 0.3)',
                          color: '#F43F5E',
                          cursor: 'pointer',
                          padding: '2px 8px',
                        }}
                      >
                        {node?.name ?? p.id} · {(p.mastery * 100).toFixed(0)}%
                      </Tag>
                    </Link>
                  )
                })}
              </div>
            </div>
          </div>
        </Card>
      )}

      <div className="mb-3">
        <Text
          style={{
            fontSize: 11,
            color: 'var(--color-mist)',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
          }}
        >
          推荐学习路径 · SM-2 排序
        </Text>
      </div>

      {graphLoading ? (
        <Row gutter={[16, 16]}>
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Col key={i} xs={24} sm={12} md={8}>
              <Card bordered={false} className="lumen-card">
                <Skeleton active paragraph={{ rows: 2 }} />
              </Card>
            </Col>
          ))}
        </Row>
      ) : nodes.length === 0 ? (
        <EmptyState
          title="知识库尚未初始化"
          description="请联系管理员或教师添加知识点到知识图谱"
        />
      ) : (
        <Row gutter={[16, 16]}>
          {learningOrder.map((id, idx) => {
            const node = nodes.find((n) => n.id === id)
            if (!node) return null
            const mastery = progress[id] ?? 0
            const isMastered = mastery >= 0.8
            return (
              <Col key={id} xs={24} sm={12} md={8}>
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(idx * 0.04, 0.4) }}
                >
                  <Link to={`/learn/${id}`}>
                    <Card
                      bordered={false}
                      hoverable
                      className="lumen-card lumen-card-hover"
                      style={{ height: '100%' }}
                    >
                      <div className="flex items-start justify-between mb-3">
                        <div
                          className="flex items-center justify-center"
                          style={{
                            width: 36,
                            height: 36,
                            borderRadius: 8,
                            background: isMastered
                              ? 'rgba(16, 185, 129, 0.12)'
                              : 'var(--color-moss-50)',
                            color: isMastered ? '#10B981' : 'var(--color-moss)',
                            fontFamily: 'var(--font-serif)',
                            fontWeight: 600,
                            fontSize: 14,
                          }}
                        >
                          {String(idx + 1).padStart(2, '0')}
                        </div>
                        <Tag
                          style={{
                            fontSize: 11,
                            margin: 0,
                            padding: '0 6px',
                            lineHeight: '18px',
                            background: 'transparent',
                            border: `1px solid var(--color-line)`,
                            color: 'var(--color-mist)',
                          }}
                        >
                          难度 {node.difficulty}
                        </Tag>
                      </div>
                      <Title
                        level={5}
                        style={{
                          margin: '0 0 4px',
                          fontFamily: 'var(--font-serif)',
                          fontWeight: 600,
                        }}
                      >
                        {node.name}
                      </Title>
                      <div className="mt-3">
                        <MasteryBar mastery={mastery} size="small" />
                      </div>
                      {node.prerequisites.length > 0 && (
                        <Paragraph
                          type="secondary"
                          style={{
                            fontSize: 11,
                            margin: '8px 0 0',
                            color: 'var(--color-mist)',
                          }}
                        >
                          前置: {knowledgeNames(nodes, node.prerequisites).join('、')}
                        </Paragraph>
                      )}
                    </Card>
                  </Link>
                </motion.div>
              </Col>
            )
          })}
        </Row>
      )}

      <Modal
        open={joinOpen}
        title="加入班级"
        onCancel={() => setJoinOpen(false)}
        onOk={() => joinForm.submit()}
        confirmLoading={joinMutation.isPending}
        okText="加入"
        cancelText="取消"
      >
        <Form
          form={joinForm}
          layout="vertical"
          onFinish={(v) => joinMutation.mutate(v.invite_code)}
          className="mt-4"
        >
          <Form.Item
            name="invite_code"
            label="邀请码"
            rules={[{ required: true, message: '请输入教师分享的邀请码' }]}
            extra="向教师索取班级邀请码，例如 DEMOCLS01"
          >
            <Input placeholder="粘贴邀请码" autoFocus />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
