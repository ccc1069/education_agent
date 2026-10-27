import {
  Badge,
  Button,
  Card,
  Col,
  Empty,
  Pagination,
  Row,
  Segmented,
  Skeleton,
  Tag,
  Typography,
} from 'antd'
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { notificationsApi } from '@/lib/api/notifications'
import { formatDateTime, formatFromNow } from '@/lib/datetime'
import type { NotificationType } from '@/types/api'

const { Text, Title, Paragraph } = Typography

const TYPE_META: Record<NotificationType, { label: string; color: string }> = {
  review_reminder: { label: '复习提醒', color: '#F59E0B' },
  class_event: { label: '班级动态', color: '#3B82F6' },
  teacher_feedback: { label: '教师反馈', color: '#10B981' },
  system: { label: '系统', color: '#6B7280' },
}

export default function NotificationsPage() {
  const qc = useQueryClient()
  const [filter, setFilter] = useState<'all' | 'unread'>('all')
  const [page, setPage] = useState(1)
  const pageSize = 20

  const { data, isLoading } = useQuery({
    queryKey: ['notifications', 'list', filter, page],
    queryFn: () =>
      notificationsApi.list({
        limit: pageSize,
        offset: (page - 1) * pageSize,
        unread_only: filter === 'unread',
      }),
  })

  const markReadMutation = useMutation({
    mutationFn: (id: number) => notificationsApi.markRead(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  })

  const markAllMutation = useMutation({
    mutationFn: () => notificationsApi.markAllRead(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  })

  const items = data?.items ?? []

  return (
    <div className="max-w-4xl mx-auto">
      <PageHeader
        title="通知中心"
        subtitle={`${data?.total_unread ?? 0} 条未读通知`}
        extra={
          <Button
            onClick={() => markAllMutation.mutate()}
            disabled={!items.some((i) => i.status !== 'read')}
            loading={markAllMutation.isPending}
          >
            全部已读
          </Button>
        }
      />

      <Card bordered={false} className="lumen-card mb-4" size="small">
        <Segmented
          value={filter}
          onChange={(v) => {
            setFilter(v as 'all' | 'unread')
            setPage(1)
          }}
          options={[
            { label: '全部', value: 'all' },
            { label: '未读', value: 'unread' },
          ]}
        />
      </Card>

      {isLoading ? (
        <Card bordered={false} className="lumen-card">
          <Skeleton active paragraph={{ rows: 6 }} />
        </Card>
      ) : items.length === 0 ? (
        <EmptyState
          title={filter === 'unread' ? '没有未读通知' : '暂无通知'}
          description={
            filter === 'unread'
              ? '所有通知都已读过'
              : '系统会在复习时间到、教师反馈等场景下推送通知'
          }
        />
      ) : (
        <div className="space-y-3">
          {items.map((item, idx) => {
            const meta = TYPE_META[item.type]
            const isUnread = item.status !== 'read'
            return (
              <Card
                key={item.id}
                bordered={false}
                className="lumen-card lumen-card-hover"
                style={{
                  borderLeft: `3px solid ${meta.color}`,
                  opacity: isUnread ? 1 : 0.65,
                }}
              >
                <div className="flex items-start gap-3">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge dot={isUnread} color={meta.color} offset={[0, 0]}>
                        <Text strong style={{ fontSize: 14 }}>
                          {item.title}
                        </Text>
                      </Badge>
                      <Tag
                        style={{
                          fontSize: 10,
                          margin: 0,
                          padding: '0 6px',
                          lineHeight: '16px',
                          background: `${meta.color}11`,
                          border: `1px solid ${meta.color}33`,
                          color: meta.color,
                        }}
                      >
                        {meta.label}
                      </Tag>
                      {item.priority >= 2 && (
                        <Tag color="error" style={{ fontSize: 10, margin: 0, padding: '0 6px', lineHeight: '16px' }}>
                          高优先级
                        </Tag>
                      )}
                    </div>
                    <Paragraph
                      style={{
                        margin: 0,
                        fontSize: 13,
                        color: 'var(--color-mist-dark)',
                        lineHeight: 1.6,
                      }}
                    >
                      {item.body}
                    </Paragraph>
                    <Text type="secondary" style={{ fontSize: 11, marginTop: 6, display: 'block' }}>
                      {formatDateTime(item.created_at)} · {formatFromNow(item.created_at)}
                      {item.read_at && ` · 已读于 ${formatDateTime(item.read_at, 'MM-DD HH:mm')}`}
                    </Text>
                  </div>
                  {isUnread && (
                    <Button
                      size="small"
                      type="text"
                      onClick={() => markReadMutation.mutate(item.id)}
                      loading={markReadMutation.isPending}
                    >
                      标记已读
                    </Button>
                  )}
                </div>
              </Card>
            )
          })}

          <div className="flex justify-end mt-4">
            <Pagination
              current={page}
              pageSize={pageSize}
              total={data?.total_unread && filter === 'unread' ? data.total_unread : items.length}
              onChange={setPage}
              showSizeChanger={false}
            />
          </div>
        </div>
      )}
    </div>
  )
}
