import { useState } from 'react'
import {
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Row,
  Skeleton,
  Table,
  Tag,
  Typography,
} from 'antd'
import { ExclamationCircleOutlined, TeamOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { formatDateTime } from '@/lib/datetime'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { StatCard } from '@/components/ui/StatCard'
import { MasteryBar } from '@/components/learner/MasteryBar'
import { teacherApi } from '@/lib/api/teacher'
import { learnerApi } from '@/lib/api/learner'
import { knowledgeName } from '@/lib/knowledgeLabel'
import type { DashboardIntervention, MemberInfo, WeakKnowledgeItem } from '@/types/api'

const { Text, Title, Paragraph } = Typography

export default function ClassDetailPage() {
  const { id } = useParams<{ id: string }>()
  const classId = Number(id)
  const { message, modal } = App.useApp()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [tab, setTab] = useState<'members' | 'dashboard'>('members')

  const { data: cls, isLoading } = useQuery({
    queryKey: ['teacher', 'class', classId],
    queryFn: () => teacherApi.getClass(classId),
    enabled: !!classId,
  })

  const { data: members } = useQuery({
    queryKey: ['teacher', 'class', classId, 'members'],
    queryFn: () => teacherApi.listMembers(classId),
    enabled: !!classId,
  })

  const { data: dashboard, isLoading: dashLoading } = useQuery({
    queryKey: ['teacher', 'class', classId, 'dashboard'],
    queryFn: () => teacherApi.dashboard(classId),
    enabled: !!classId && tab === 'dashboard',
  })

  const { data: graphData } = useQuery({
    queryKey: ['knowledge-graph'],
    queryFn: () => learnerApi.knowledgeGraph(),
    enabled: tab === 'dashboard',
  })

  const removeMutation = useMutation({
    mutationFn: (learnerId: number) => teacherApi.removeMember(classId, learnerId),
    onSuccess: () => {
      message.success('成员已移除')
      qc.invalidateQueries({ queryKey: ['teacher', 'class', classId] })
      qc.invalidateQueries({ queryKey: ['teacher', 'classes'] })
    },
  })

  const archiveMutation = useMutation({
    mutationFn: () => teacherApi.archiveClass(classId),
    onSuccess: () => {
      message.success('班级已归档（学生将无法再用邀请码加入）')
      qc.invalidateQueries({ queryKey: ['teacher', 'class', classId] })
      qc.invalidateQueries({ queryKey: ['teacher', 'classes'] })
    },
  })

  const handleRemove = (m: MemberInfo) => {
    modal.confirm({
      title: '确认移除成员?',
      icon: <ExclamationCircleOutlined style={{ color: '#F43F5E' }} />,
      content: `将从班级移除 ${m.name ?? m.public_id}`,
      okText: '移除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => removeMutation.mutate(m.learner_id),
    })
  }

  if (isLoading || !cls) {
    return (
      <div className="max-w-7xl mx-auto">
        <Card bordered={false} className="lumen-card">
          <Skeleton active paragraph={{ rows: 6 }} />
        </Card>
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto">
      <PageHeader
        title={cls.name}
        subtitle={cls.description ?? '班级详情 · 成员管理 · 学情分析'}
        extra={
          <div className="flex items-center gap-2">
            <Tag
              style={{
                fontFamily: 'var(--font-mono)',
                background: 'var(--color-moss-50)',
                border: '1px solid var(--color-line)',
                color: 'var(--color-moss)',
              }}
            >
              邀请码 {cls.invite_code}
            </Tag>
            <Button onClick={() => navigate('/teacher/classes')}>返回</Button>
            {cls.is_active && (
              <Button danger onClick={() => archiveMutation.mutate()} loading={archiveMutation.isPending}>
                归档
              </Button>
            )}
          </div>
        }
      />

      <Card bordered={false} className="lumen-card mb-4" size="small">
        <div className="flex gap-6">
          <button
            onClick={() => setTab('members')}
            style={{
              cursor: 'pointer',
              background: 'transparent',
              border: 'none',
              padding: 0,
            }}
          >
            <Text
              strong
              style={{
                fontSize: 14,
                color: tab === 'members' ? 'var(--color-moss)' : 'var(--color-mist)',
                borderBottom:
                  tab === 'members' ? '2px solid var(--color-moss)' : '2px solid transparent',
                paddingBottom: 4,
              }}
            >
              <TeamOutlined style={{ marginRight: 6 }} />
              成员列表 ({cls.member_count})
            </Text>
          </button>
          <button
            onClick={() => setTab('dashboard')}
            style={{
              cursor: 'pointer',
              background: 'transparent',
              border: 'none',
              padding: 0,
            }}
          >
            <Text
              strong
              style={{
                fontSize: 14,
                color: tab === 'dashboard' ? 'var(--color-moss)' : 'var(--color-mist)',
                borderBottom:
                  tab === 'dashboard' ? '2px solid var(--color-moss)' : '2px solid transparent',
                paddingBottom: 4,
              }}
            >
              学情看板
            </Text>
          </button>
        </div>
      </Card>

      {tab === 'members' ? (
        <Card bordered={false} className="lumen-card">
          {!members || members.length === 0 ? (
            <EmptyState title="还没有成员" description="分享邀请码，让学生在学习中心加入" />
          ) : (
            <Table
              dataSource={members}
              rowKey="learner_id"
              pagination={{ pageSize: 20, showSizeChanger: false }}
              columns={[
                {
                  title: '学生',
                  dataIndex: 'name',
                  key: 'name',
                  render: (name: string | null, r: MemberInfo) => (
                    <div className="flex items-center gap-2">
                      <div
                        style={{
                          width: 32,
                          height: 32,
                          borderRadius: '50%',
                          background: 'var(--color-moss-50)',
                          color: 'var(--color-moss)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: 13,
                          fontWeight: 600,
                          fontFamily: 'var(--font-serif)',
                        }}
                      >
                        {(name ?? r.public_id).slice(0, 1).toUpperCase()}
                      </div>
                      <div>
                        <Text strong style={{ fontSize: 13, display: 'block' }}>
                          {name ?? '未命名'}
                        </Text>
                        <Text
                          type="secondary"
                          style={{ fontSize: 11, fontFamily: 'var(--font-mono)' }}
                        >
                          {r.public_id}
                        </Text>
                      </div>
                    </div>
                  ),
                },
                {
                  title: '加入时间',
                  dataIndex: 'joined_at',
                  key: 'joined_at',
                  render: (t: string) => (
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {formatDateTime(t, 'YYYY-MM-DD HH:mm')}
                    </Text>
                  ),
                },
                {
                  title: '操作',
                  key: 'action',
                  width: 100,
                  render: (_: unknown, r: MemberInfo) => (
                    <Button
                      size="small"
                      type="text"
                      danger
                      onClick={() => handleRemove(r)}
                      loading={removeMutation.isPending}
                    >
                      移除
                    </Button>
                  ),
                },
              ]}
            />
          )}
        </Card>
      ) : (
        <div className="space-y-4">
          {dashLoading ? (
            <Card bordered={false} className="lumen-card">
              <Skeleton active paragraph={{ rows: 8 }} />
            </Card>
          ) : dashboard ? (
            <>
              <Row gutter={[16, 16]}>
                <Col xs={12} md={6}>
                  <StatCard title="班级人数" value={dashboard.member_count} />
                </Col>
                <Col xs={12} md={6}>
                  <StatCard
                    title="平均掌握度"
                    value={`${(dashboard.avg_mastery * 100).toFixed(0)}%`}
                    valueStyle={{ color: 'var(--color-moss)' }}
                  />
                </Col>
                <Col xs={12} md={6}>
                  <StatCard
                    title="掌握度记录数"
                    value={dashboard.total_states}
                    valueStyle={{ color: '#3B82F6' }}
                  />
                </Col>
                <Col xs={12} md={6}>
                  <StatCard
                    title="薄弱知识点"
                    value={dashboard.weak_knowledge_ids.length}
                    valueStyle={{ color: '#F43F5E' }}
                  />
                </Col>
              </Row>

              <Row gutter={[16, 16]}>
                <Col xs={24} lg={12}>
                  <Card bordered={false} className="lumen-card">
                    <Title level={5} style={{ marginTop: 0 }}>
                      薄弱知识点
                    </Title>
                    <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 12 }}>
                      班级平均掌握度低于 40% 的知识点
                    </Text>
                    {dashboard.weak_knowledge_ids.length === 0 ? (
                      <Empty
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                        description="暂无薄弱点"
                        style={{ padding: '24px 0' }}
                      />
                    ) : (
                      <div className="space-y-2">
                        {dashboard.weak_knowledge_ids.map((w: WeakKnowledgeItem) => (
                          <div
                            key={w.knowledge_id}
                            style={{
                              padding: '10px 12px',
                              background: 'var(--color-paper)',
                              borderRadius: 8,
                              border: '1px solid var(--color-line)',
                            }}
                          >
                            <div className="flex items-center justify-between gap-2 mb-1">
                              <Text strong style={{ fontSize: 13 }}>
                                {knowledgeName(graphData?.nodes, w.knowledge_id)}
                              </Text>
                              <Tag color="error" style={{ margin: 0, fontSize: 10 }}>
                                {(w.avg_mastery * 100).toFixed(0)}%
                              </Tag>
                            </div>
                            <Text type="secondary" style={{ fontSize: 11 }}>
                              {w.student_count} 名学生有记录
                            </Text>
                            <div className="mt-2">
                              <MasteryBar mastery={w.avg_mastery} size="small" showLabel={false} />
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </Card>
                </Col>

                <Col xs={24} lg={12}>
                  <Card bordered={false} className="lumen-card">
                    <Title level={5} style={{ marginTop: 0 }}>
                      班级概览
                    </Title>
                    <Descriptions column={1} size="small">
                      <Descriptions.Item label="班级 ID">{dashboard.class_id}</Descriptions.Item>
                      <Descriptions.Item label="班级名称">{dashboard.class_name}</Descriptions.Item>
                      <Descriptions.Item label="成员总数">{dashboard.member_count}</Descriptions.Item>
                      <Descriptions.Item label="掌握度记录数">
                        {dashboard.total_states}
                      </Descriptions.Item>
                    </Descriptions>
                  </Card>
                </Col>
              </Row>

              <Card bordered={false} className="lumen-card">
                <Title level={5} style={{ marginTop: 0 }}>
                  个体干预建议
                </Title>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  规则：掌握度 &lt; 20% 且练习次数 ≥ 3（基于 BKT，非实时情绪监测）
                </Text>
                {dashboard.interventions.length === 0 ? (
                  <EmptyState title="暂无干预建议" description="暂无满足规则的学生" />
                ) : (
                  <div className="mt-4 space-y-3">
                    {dashboard.interventions.map((itv: DashboardIntervention) => (
                      <div
                        key={`${itv.learner_id}-${itv.knowledge_id}`}
                        style={{
                          padding: 14,
                          background: 'var(--color-paper)',
                          borderRadius: 8,
                          border: '1px solid rgba(244, 63, 94, 0.2)',
                          borderLeft: '3px solid #F43F5E',
                        }}
                      >
                        <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
                          <div className="flex items-center gap-2 flex-wrap">
                            <Text strong style={{ fontSize: 13 }}>
                              {itv.name ?? itv.public_id ?? `学习者 #${itv.learner_id}`}
                            </Text>
                            <Tag color="error" style={{ margin: 0, fontSize: 10 }}>
                              {knowledgeName(graphData?.nodes, itv.knowledge_id)}
                            </Tag>
                            <Text type="secondary" style={{ fontSize: 11 }}>
                              练习 {itv.attempts} 次
                            </Text>
                          </div>
                          <div style={{ width: 120 }}>
                            <MasteryBar mastery={itv.mastery} size="small" showLabel />
                          </div>
                        </div>
                        <Paragraph
                          style={{
                            margin: 0,
                            fontSize: 13,
                            color: 'var(--color-mist-dark)',
                            lineHeight: 1.6,
                          }}
                        >
                          {itv.recommendation}
                        </Paragraph>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </>
          ) : (
            <EmptyState title="暂无看板数据" description="等待学生开始学习后才会有数据" />
          )}
        </div>
      )}
    </div>
  )
}
