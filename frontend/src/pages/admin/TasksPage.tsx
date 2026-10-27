import { useState } from 'react'
import {
  App,
  Button,
  Card,
  Col,
  Empty,
  Row,
  Segmented,
  Skeleton,
  Statistic,
  Tag,
  Typography,
} from 'antd'
import {
  PlayCircleOutlined,
  ClockCircleOutlined,
  HistoryOutlined,
  ThunderboltOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { formatDateTime } from '@/lib/datetime'
import { motion } from 'motion/react'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { StatCard } from '@/components/ui/StatCard'
import { tasksApi, type TaskHistoryParams } from '@/lib/api/tasks'
import type { TaskInfo, TaskScheduleInfo } from '@/types/api'

const { Text, Title, Paragraph } = Typography

function formatSchedule(schedule: string | TaskScheduleInfo | undefined): string | null {
  if (!schedule) return null
  if (typeof schedule === 'string') return schedule
  const parts: string[] = []
  if (schedule.type === 'cron' && schedule.expr) parts.push(`cron ${schedule.expr}`)
  else if (schedule.type === 'interval' && schedule.seconds != null) {
    parts.push(schedule.seconds >= 3600 ? `每 ${schedule.seconds / 3600} 小时` : `每 ${schedule.seconds}s`)
  } else if (schedule.trigger) parts.push(schedule.trigger)
  else if (schedule.expr) parts.push(`cron ${schedule.expr}`)
  else if (schedule.seconds != null) parts.push(`每 ${schedule.seconds}s`)
  if (schedule.next_run_at) {
    parts.push(`下次 ${formatDateTime(schedule.next_run_at, 'MM-DD HH:mm')}`)
  }
  return parts.join(' · ') || null
}

const STATUS_COLORS: Record<string, string> = {
  success: '#10B981',
  failed: '#F43F5E',
  running: '#3B82F6',
  pending: '#F59E0B',
  cancelled: '#6B7280',
}

const STATUS_LABELS: Record<string, string> = {
  success: '成功',
  failed: '失败',
  running: '运行中',
  pending: '等待',
  cancelled: '已取消',
}

const CATEGORY_COLORS: Record<string, string> = {
  engagement: '#D97757',
  privacy: '#F43F5E',
  maintenance: '#6B7280',
  analytics: '#10B981',
  curriculum: '#F59E0B',
  rag: '#3B82F6',
  cleanup: '#6B7280',
  notification: '#8B5CF6',
}

const CATEGORY_LABELS: Record<string, string> = {
  engagement: '学习提醒',
  privacy: '隐私合规',
  maintenance: '系统维护',
  analytics: '运营统计',
}

const QUEUE_STAT_LABELS: Record<string, string> = {
  enqueued: '已入队',
  succeeded: '执行成功',
  failed: '执行失败',
  retried: '重试次数',
  queue_size: '队列长度',
  dead_letters: '死信数量',
  running: '队列运行中',
  size: '队列长度',
}

export default function TasksPage() {
  const { message, modal } = App.useApp()
  const qc = useQueryClient()
  const [historyFilter, setHistoryFilter] = useState<'all' | 'success' | 'failed'>('all')
  const [triggeringName, setTriggeringName] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'tasks'],
    queryFn: () => tasksApi.list(),
    refetchInterval: 15_000,
  })

  const historyParams: TaskHistoryParams = {
    limit: 50,
    status: historyFilter === 'all' ? undefined : historyFilter,
  }

  const { data: history, isLoading: historyLoading } = useQuery({
    queryKey: ['admin', 'tasks', 'history', historyParams],
    queryFn: () => tasksApi.history(historyParams),
    refetchInterval: 15_000,
  })

  const { data: deadLetters = [] } = useQuery({
    queryKey: ['admin', 'tasks', 'dead-letters'],
    queryFn: () => tasksApi.deadLetters(),
    refetchInterval: 30_000,
  })

  const triggerMutation = useMutation({
    mutationFn: (taskName: string) => tasksApi.trigger(taskName),
    onMutate: (taskName) => setTriggeringName(taskName),
    onSettled: () => setTriggeringName(null),
    onSuccess: (res) => {
      if (res.error || res.status === 'failed') {
        message.error(`任务失败: ${res.error ?? res.status}`)
      } else {
        message.success(`任务 ${res.task_name} 已执行 (${res.status})`)
      }
      qc.invalidateQueries({ queryKey: ['admin', 'tasks'] })
      qc.invalidateQueries({ queryKey: ['admin', 'tasks', 'history'] })
      qc.invalidateQueries({ queryKey: ['admin', 'tasks', 'dead-letters'] })
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        '触发失败'
      message.error(detail)
    },
  })

  const handleTrigger = (task: TaskInfo) => {
    modal.confirm({
      title: '确认立即执行任务?',
      content: (
        <div>
          <Paragraph style={{ marginTop: 8 }}>
            <Text strong>{task.name}</Text>: {task.description}
          </Paragraph>
          <Paragraph type="secondary" style={{ fontSize: 12 }}>
            将立即执行一次并写入执行历史，可在右侧查看结果。
          </Paragraph>
        </div>
      ),
      okText: '执行',
      cancelText: '取消',
      onOk: () => triggerMutation.mutateAsync(task.name),
    })
  }

  const registered = Array.isArray(data?.registered) ? data.registered : []
  const queueStats =
    data?.queue_stats && typeof data.queue_stats === 'object' ? data.queue_stats : {}
  const historyList = Array.isArray(history) ? history : []
  const successCount = historyList.filter((h) => h.status === 'success').length
  const failedCount = historyList.filter((h) => h.status === 'failed').length
  const queueSize =
    typeof queueStats.queue_size === 'number'
      ? queueStats.queue_size
      : typeof queueStats.size === 'number'
        ? queueStats.size
        : 0
  const deadLetterCount =
    Array.isArray(deadLetters) && deadLetters.length > 0
      ? deadLetters.length
      : typeof queueStats.dead_letters === 'number'
        ? queueStats.dead_letters
        : 0

  return (
    <div className="max-w-7xl mx-auto">
      <PageHeader
        title="任务调度"
        subtitle="APScheduler · 北京时间 · 手动执行写入历史"
      />

      <Row gutter={[16, 16]} className="mb-6">
        <Col xs={12} md={6}>
          <StatCard title="注册任务" value={registered.length} loading={isLoading} />
        </Col>
        <Col xs={12} md={6}>
          <StatCard
            title="近期成功"
            value={successCount}
            valueStyle={{ color: '#10B981' }}
            loading={historyLoading}
          />
        </Col>
        <Col xs={12} md={6}>
          <StatCard
            title="近期失败"
            value={failedCount}
            valueStyle={{ color: '#F43F5E' }}
            loading={historyLoading}
          />
        </Col>
        <Col xs={12} md={6}>
          <StatCard
            title="队列 / 死信"
            value={`${queueSize} / ${deadLetterCount}`}
            valueStyle={{ color: '#3B82F6', fontSize: 22 }}
            loading={isLoading}
          />
        </Col>
      </Row>
      <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: -12, marginBottom: 16 }}>
        「近期成功/失败」统计当前筛选下最多 50 条执行记录，非全库累计。
      </Text>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card bordered={false} className="lumen-card">
            <Title level={5} style={{ marginTop: 0 }}>
              <ThunderboltOutlined style={{ marginRight: 6, color: 'var(--color-moss)' }} />
              已注册任务
            </Title>
            {isLoading ? (
              <Skeleton active paragraph={{ rows: 6 }} />
            ) : registered.length === 0 ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="暂无注册任务"
                style={{ padding: '24px 0' }}
              />
            ) : (
              <div className="space-y-3">
                {registered.map((task) => {
                  const catColor = CATEGORY_COLORS[task.category] ?? '#6B7280'
                  const scheduleText = formatSchedule(task.schedule)
                  return (
                    <div
                      key={task.name}
                      style={{
                        padding: 12,
                        background: 'var(--color-paper)',
                        borderRadius: 8,
                        border: '1px solid var(--color-line)',
                        borderLeft: `3px solid ${catColor}`,
                      }}
                    >
                      <div className="flex items-start justify-between gap-2 mb-1">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1 flex-wrap">
                            <Text
                              strong
                              style={{
                                fontSize: 13,
                                fontFamily: 'var(--font-mono)',
                                color: 'var(--color-ink)',
                              }}
                            >
                              {task.name}
                            </Text>
                            <Tag
                              style={{
                                fontSize: 10,
                                margin: 0,
                                padding: '0 6px',
                                lineHeight: '16px',
                                background: `${catColor}11`,
                                border: `1px solid ${catColor}33`,
                                color: catColor,
                              }}
                            >
                              {CATEGORY_LABELS[task.category] ?? task.category}
                            </Tag>
                          </div>
                          <Paragraph
                            type="secondary"
                            style={{
                              fontSize: 12,
                              margin: 0,
                              lineHeight: 1.5,
                            }}
                          >
                            {task.description}
                          </Paragraph>
                          {scheduleText && (
                            <Text
                              type="secondary"
                              style={{
                                fontSize: 11,
                                fontFamily: 'var(--font-mono)',
                                display: 'block',
                                marginTop: 4,
                              }}
                            >
                              <ClockCircleOutlined style={{ marginRight: 4 }} />
                              {scheduleText}
                            </Text>
                          )}
                        </div>
                        <Button
                          size="small"
                          type="primary"
                          ghost
                          icon={<PlayCircleOutlined />}
                          onClick={() => handleTrigger(task)}
                          loading={triggeringName === task.name}
                        >
                          执行
                        </Button>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card bordered={false} className="lumen-card">
            <div className="flex items-center justify-between mb-3">
              <Title level={5} style={{ margin: 0 }}>
                <HistoryOutlined style={{ marginRight: 6, color: 'var(--color-moss)' }} />
                执行历史
              </Title>
              <Segmented
                size="small"
                value={historyFilter}
                onChange={(v) => setHistoryFilter(v as 'all' | 'success' | 'failed')}
                options={[
                  { label: '全部', value: 'all' },
                  { label: '成功', value: 'success' },
                  { label: '失败', value: 'failed' },
                ]}
              />
            </div>
            {historyLoading ? (
              <Skeleton active paragraph={{ rows: 8 }} />
            ) : historyList.length === 0 ? (
              <EmptyState title="暂无执行记录" description="点击左侧「执行」后会立即出现在此" />
            ) : (
              <div className="space-y-2" style={{ maxHeight: 600, overflowY: 'auto' }}>
                {historyList.map((h, idx) => {
                  const color = STATUS_COLORS[h.status] ?? '#6B7280'
                  return (
                    <motion.div
                      key={h.id}
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: Math.min(idx * 0.02, 0.3) }}
                      style={{
                        padding: 10,
                        background: 'var(--color-paper)',
                        borderRadius: 6,
                        border: '1px solid var(--color-line)',
                      }}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center gap-2 min-w-0">
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
                            {STATUS_LABELS[h.status] ?? h.status}
                          </Tag>
                          <Text
                            strong
                            style={{
                              fontSize: 12,
                              fontFamily: 'var(--font-mono)',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {h.task_name}
                          </Text>
                        </div>
                        {h.duration_ms != null && (
                          <Text type="secondary" style={{ fontSize: 10, fontFamily: 'var(--font-mono)' }}>
                            {h.duration_ms < 1000
                              ? `${h.duration_ms}ms`
                              : `${(h.duration_ms / 1000).toFixed(2)}s`}
                          </Text>
                        )}
                      </div>
                      <div className="flex items-center justify-between">
                        <Text type="secondary" style={{ fontSize: 10 }}>
                          {formatDateTime(h.started_at)}
                          {h.triggered_by && ` · ${h.triggered_by}`}
                        </Text>
                      </div>
                      {h.error_message && (
                        <Paragraph
                          type="danger"
                          style={{
                            fontSize: 11,
                            margin: '4px 0 0',
                            lineHeight: 1.4,
                          }}
                          ellipsis={{ rows: 2 }}
                        >
                          {h.error_message}
                        </Paragraph>
                      )}
                    </motion.div>
                  )
                })}
              </div>
            )}
          </Card>
        </Col>
      </Row>

      <Card bordered={false} className="lumen-card mt-4">
        <Title level={5} style={{ marginTop: 0 }}>
          队列统计
        </Title>
        {Object.keys(queueStats).length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="暂无队列数据"
            style={{ padding: '24px 0' }}
          />
        ) : (
          <Row gutter={[16, 12]}>
            {Object.entries(queueStats).map(([k, v]) => {
              let display: string
              if (typeof v === 'boolean') display = v ? '是' : '否'
              else if (typeof v === 'number') display = String(v)
              else display = JSON.stringify(v)
              return (
                <Col key={k} xs={12} md={6}>
                  <Statistic
                    title={
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {QUEUE_STAT_LABELS[k] ?? k}
                      </Text>
                    }
                    value={display}
                    valueStyle={{
                      fontSize: 20,
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--color-moss)',
                    }}
                  />
                </Col>
              )
            })}
          </Row>
        )}
      </Card>

      {Array.isArray(deadLetters) && deadLetters.length > 0 && (
        <Card bordered={false} className="lumen-card mt-4">
          <Title level={5} style={{ marginTop: 0 }}>
            <WarningOutlined style={{ marginRight: 6, color: '#F43F5E' }} />
            死信队列
          </Title>
          <div className="space-y-2">
            {deadLetters.map((dl, i) => {
              const item = dl as {
                task_name?: string
                last_error?: string
                failed_at?: string
                triggered_by?: string
              }
              return (
                <div
                  key={`${item.task_name}-${i}`}
                  style={{
                    padding: 10,
                    background: 'rgba(244, 63, 94, 0.04)',
                    border: '1px solid rgba(244, 63, 94, 0.2)',
                    borderRadius: 6,
                  }}
                >
                  <Text strong style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                    {item.task_name ?? 'unknown'}
                  </Text>
                  <div>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {item.triggered_by ?? ''}
                      {item.failed_at ? ` · ${formatDateTime(item.failed_at)}` : ''}
                    </Text>
                  </div>
                  {item.last_error && (
                    <Paragraph type="danger" style={{ fontSize: 11, margin: '4px 0 0' }} ellipsis={{ rows: 2 }}>
                      {item.last_error}
                    </Paragraph>
                  )}
                </div>
              )
            })}
          </div>
        </Card>
      )}
    </div>
  )
}
