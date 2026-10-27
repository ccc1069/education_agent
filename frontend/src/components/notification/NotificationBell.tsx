import { Badge, Dropdown, Empty, List, Typography, App } from 'antd'
import { BellOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { formatFromNow } from '@/lib/datetime'
import { notificationsApi } from '@/lib/api/notifications'
import type { NotificationItem } from '@/types/api'

const { Text, Title } = Typography

export function NotificationBell() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data: countData } = useQuery({
    queryKey: ['notifications', 'unread-count'],
    queryFn: () => notificationsApi.unreadCount(),
    refetchInterval: 30_000,
  })

  const { data, isLoading } = useQuery({
    queryKey: ['notifications', 'recent'],
    queryFn: () => notificationsApi.list({ limit: 5, unread_only: true }),
    refetchInterval: 30_000,
  })

  const markReadMutation = useMutation({
    mutationFn: (id: number) => notificationsApi.markRead(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notifications'] })
    },
  })

  const markAllMutation = useMutation({
    mutationFn: () => notificationsApi.markAllRead(),
    onSuccess: (res) => {
      message.success(`已标记 ${res.marked} 条为已读`)
      qc.invalidateQueries({ queryKey: ['notifications'] })
    },
  })

  const unread = countData?.unread ?? 0
  const items = data?.items ?? []

  return (
    <Dropdown
      trigger={['click']}
      placement="bottomRight"
      dropdownRender={() => (
        <div
          style={{
            width: 360,
            background: 'var(--color-card)',
            borderRadius: 12,
            border: '1px solid var(--color-line)',
            boxShadow: 'var(--shadow-lift)',
            padding: 12,
          }}
        >
          <div className="flex items-center justify-between mb-3 px-1">
            <Title level={5} style={{ margin: 0 }}>
              通知
            </Title>
            <button
              className="text-xs cursor-pointer"
              style={{
                color: 'var(--color-moss)',
                background: 'transparent',
                border: 'none',
                padding: 0,
              }}
              onClick={() => markAllMutation.mutate()}
              disabled={items.length === 0}
            >
              全部已读
            </button>
          </div>
          {items.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暂无未读通知"
              style={{ padding: '24px 0' }}
            />
          ) : (
            <List
              loading={isLoading}
              dataSource={items}
              renderItem={(item: NotificationItem) => (
                <List.Item
                  style={{ padding: '8px 4px', cursor: 'pointer', borderRadius: 6 }}
                  onClick={() => {
                    markReadMutation.mutate(item.id)
                  }}
                >
                  <div className="w-full">
                    <div className="flex items-start justify-between gap-2">
                      <Text strong style={{ fontSize: 13 }}>
                        {item.title}
                      </Text>
                      <Text type="secondary" style={{ fontSize: 11, flexShrink: 0 }}>
                        {formatFromNow(item.created_at)}
                      </Text>
                    </div>
                    <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 2 }}>
                      {item.body}
                    </Text>
                  </div>
                </List.Item>
              )}
            />
          )}
          <div
            style={{
              borderTop: '1px solid var(--color-line)',
              marginTop: 8,
              paddingTop: 8,
              textAlign: 'center',
            }}
          >
            <button
              className="text-xs cursor-pointer"
              style={{
                color: 'var(--color-moss)',
                background: 'transparent',
                border: 'none',
                padding: '4px 0',
                width: '100%',
              }}
              onClick={() => navigate('/notifications')}
            >
              查看全部通知 →
            </button>
          </div>
        </div>
      )}
    >
      <Badge count={unread} size="small" offset={[-2, 2]}>
        <button
          aria-label="通知"
          className="cursor-pointer"
          style={{
            width: 36,
            height: 36,
            borderRadius: 8,
            border: '1px solid var(--color-line)',
            background: 'var(--color-card)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <BellOutlined style={{ fontSize: 16, color: 'var(--color-ink)' }} />
        </button>
      </Badge>
    </Dropdown>
  )
}
