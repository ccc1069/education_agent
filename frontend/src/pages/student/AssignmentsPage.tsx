import { Button, Card, Segmented, Skeleton, Table, Tag, Typography } from 'antd'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { teacherApi } from '@/lib/api/teacher'
import { formatDateTime } from '@/lib/datetime'
import type { AssignmentSummary } from '@/types/api'

const { Text, Paragraph } = Typography

const STATUS_META: Record<'published' | 'closed', { label: string; color: string }> = {
  published: { label: '进行中', color: '#10B981' },
  closed: { label: '已截止', color: '#F59E0B' },
}

type Filter = 'all' | 'published' | 'closed'

export default function StudentAssignmentsPage() {
  const [filter, setFilter] = useState<Filter>('all')

  const { data: assignments, isLoading } = useQuery({
    queryKey: ['student', 'assignments'],
    queryFn: () => teacherApi.listMyAssignments(),
  })

  const filtered = (assignments ?? []).filter((a) =>
    filter === 'all' ? true : a.status === filter,
  )

  return (
    <div className="max-w-5xl mx-auto">
      <PageHeader
        title="我的作业"
        subtitle="所在班级已发布或已关闭的作业；作答请前往练习题库（本页不统计提交进度）"
        extra={
          <Link to="/practice">
            <Button type="primary">去练习题库</Button>
          </Link>
        }
      />

      <Card bordered={false} className="lumen-card mb-4" size="small">
        <Segmented
          value={filter}
          onChange={(v) => setFilter(v as Filter)}
          options={[
            { label: '全部', value: 'all' },
            { label: '进行中', value: 'published' },
            { label: '已截止', value: 'closed' },
          ]}
        />
      </Card>

      {isLoading ? (
        <Card bordered={false} className="lumen-card">
          <Skeleton active paragraph={{ rows: 5 }} />
        </Card>
      ) : filtered.length === 0 ? (
        <EmptyState
          title="暂无作业"
          description="加入班级后，教师发布的作业会出现在这里"
        />
      ) : (
        <Card bordered={false} className="lumen-card">
          <Table
            dataSource={filtered}
            rowKey="id"
            pagination={{ pageSize: 12, showSizeChanger: false }}
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
                key: 'class',
                width: 140,
                render: (_: unknown, r: AssignmentSummary) => (
                  <Tag
                    style={{
                      fontSize: 11,
                      margin: 0,
                      background: 'var(--color-moss-50)',
                      border: '1px solid var(--color-line)',
                      color: 'var(--color-moss)',
                    }}
                  >
                    {r.class_name ?? `#${r.class_id}`}
                  </Tag>
                ),
              },
              {
                title: '题目数',
                dataIndex: 'question_ids',
                key: 'count',
                width: 80,
                render: (ids: number[]) => (
                  <Text style={{ fontSize: 13, fontFamily: 'var(--font-mono)' }}>{ids.length}</Text>
                ),
              },
              {
                title: '状态',
                dataIndex: 'status',
                key: 'status',
                width: 100,
                render: (s: AssignmentSummary['status']) => {
                  if (s !== 'published' && s !== 'closed') return null
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
            ]}
          />
        </Card>
      )}
    </div>
  )
}
