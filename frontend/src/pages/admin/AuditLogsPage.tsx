import { useState } from 'react'
import {
  App,
  Button,
  Card,
  Col,
  Input,
  Row,
  Skeleton,
  Tag,
  Typography,
} from 'antd'
import {
  SafetyCertificateOutlined,
  LinkOutlined,
  WarningOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { formatDateTime } from '@/lib/datetime'
import { motion } from 'motion/react'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { StatCard } from '@/components/ui/StatCard'
import { auditApi } from '@/lib/api/audit'

const { Text } = Typography

const ACTION_COLORS: Record<string, string> = {
  'auth.login': '#3B82F6',
  'auth.logout': '#6B7280',
  'auth.register': '#10B981',
  'auth.register_staff': '#059669',
  'practice.submit': '#8B5CF6',
  'class.create': '#10B981',
  'class.join': '#3B82F6',
  'class.archive': '#F59E0B',
  'class.member_remove': '#F43F5E',
  'assignment.create': '#10B981',
  'assignment.publish': '#0891B2',
  'assignment.status_change': '#F59E0B',
  'assignment.delete': '#F43F5E',
  consent_set: '#D97757',
  data_export: '#0891B2',
  deletion_requested: '#F43F5E',
  deletion_cancelled: '#6B7280',
  login: '#3B82F6',
  logout: '#6B7280',
  create: '#10B981',
  update: '#F59E0B',
  delete: '#F43F5E',
  submit: '#8B5CF6',
}

export default function AuditLogsPage() {
  const { message } = App.useApp()
  const qc = useQueryClient()
  const [actorFilter, setActorFilter] = useState('')
  const [actionFilter, setActionFilter] = useState('')

  const params: { limit: number; actor?: string; action?: string } = { limit: 100 }
  if (actorFilter.trim()) params.actor = actorFilter.trim()
  if (actionFilter.trim()) params.action = actionFilter.trim()

  const { data: logs, isLoading } = useQuery({
    queryKey: ['audit', 'logs', params],
    queryFn: () => auditApi.list(params),
  })

  const { data: verifyResult, isLoading: verifying } = useQuery({
    queryKey: ['audit', 'verify'],
    queryFn: () => auditApi.verify(),
  })

  const totalChecked = logs?.length ?? 0

  return (
    <div className="max-w-7xl mx-auto">
      <PageHeader
        title="审计日志"
        subtitle="登录 · 练习 · 班级作业 · 隐私操作 · HMAC 链防篡改"
        extra={
          <Button
            icon={<SafetyCertificateOutlined />}
            onClick={() => {
              qc.invalidateQueries({ queryKey: ['audit', 'verify'] })
              message.success('已重新校验哈希链')
            }}
            loading={verifying}
          >
            重新校验
          </Button>
        }
      />

      {/* 哈希链校验状态 */}
      <Card bordered={false} className="lumen-card mb-4">
        {verifying ? (
          <Skeleton active paragraph={{ rows: 2 }} />
        ) : verifyResult ? (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              {verifyResult.valid ? (
                <div
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: '50%',
                    background: 'rgba(16, 185, 129, 0.12)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <SafetyCertificateOutlined style={{ fontSize: 24, color: '#10B981' }} />
                </div>
              ) : (
                <div
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: '50%',
                    background: 'rgba(244, 63, 94, 0.12)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <WarningOutlined style={{ fontSize: 24, color: '#F43F5E' }} />
                </div>
              )}
              <div>
                <Text
                  strong
                  style={{
                    fontSize: 16,
                    fontFamily: 'var(--font-serif)',
                    color: verifyResult.valid ? '#10B981' : '#F43F5E',
                  }}
                >
                  {verifyResult.valid ? '哈希链完整 · 无篡改' : '哈希链断裂 · 检测到篡改'}
                </Text>
                <div>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    已校验 {verifyResult.checked} 条记录
                    {verifyResult.broken_at !== null &&
                      ` · 断裂点 #${verifyResult.broken_at}`}
                  </Text>
                </div>
              </div>
            </div>
            <Tag
              color={verifyResult.valid ? 'success' : 'error'}
              style={{ fontSize: 12, padding: '4px 12px' }}
            >
              {verifyResult.valid ? 'CHAIN VALID' : 'CHAIN BROKEN'}
            </Tag>
          </div>
        ) : null}
      </Card>

      <Row gutter={[16, 16]} className="mb-4">
        <Col xs={12} md={8}>
          <StatCard title="日志总数" value={totalChecked} loading={isLoading} />
        </Col>
        <Col xs={12} md={8}>
          <StatCard
            title="最新记录"
            value={logs?.[0] ? formatDateTime(logs[0].created_at, 'MM-DD HH:mm:ss') : '-'}
            valueStyle={{ fontSize: 18, fontFamily: 'var(--font-mono)' }}
            loading={isLoading}
          />
        </Col>
        <Col xs={12} md={8}>
          <StatCard
            title="独立操作者"
            value={new Set(logs?.map((l) => l.actor) ?? []).size}
            valueStyle={{ color: 'var(--color-moss)' }}
            loading={isLoading}
          />
        </Col>
      </Row>

      {/* 过滤器 */}
      <Card bordered={false} className="lumen-card mb-4" size="small">
        <Row gutter={[12, 12]} align="middle">
          <Col xs={24} md={10}>
            <Input
              prefix={<SearchOutlined />}
              placeholder="按操作者过滤 (邮箱/ID)"
              value={actorFilter}
              onChange={(e) => setActorFilter(e.target.value)}
              allowClear
            />
          </Col>
          <Col xs={24} md={10}>
            <Input
              prefix={<SearchOutlined />}
              placeholder="按操作类型过滤 (auth.login / practice.submit / class.create...)"
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              allowClear
            />
          </Col>
          <Col xs={24} md={4}>
            <Button
              block
              icon={<ReloadOutlined />}
              onClick={() => {
                setActorFilter('')
                setActionFilter('')
              }}
            >
              重置
            </Button>
          </Col>
        </Row>
      </Card>

      {/* 日志列表 */}
      {isLoading ? (
        <Card bordered={false} className="lumen-card">
          <Skeleton active paragraph={{ rows: 8 }} />
        </Card>
      ) : !logs || logs.length === 0 ? (
        <EmptyState
          title="暂无审计日志"
          description="登录、练习提交、班级/作业变更与隐私操作会自动记录"
        />
      ) : (
        <Card bordered={false} className="lumen-card">
          <div className="space-y-2">
            {logs.map((log, idx) => {
              const color = ACTION_COLORS[log.action] ?? '#6B7280'
              return (
                <motion.div
                  key={log.id}
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: Math.min(idx * 0.01, 0.2) }}
                  style={{
                    padding: 12,
                    background: 'var(--color-paper)',
                    borderRadius: 8,
                    border: '1px solid var(--color-line)',
                    borderLeft: `3px solid ${color}`,
                  }}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <Tag
                          style={{
                            fontSize: 10,
                            margin: 0,
                            padding: '0 6px',
                            lineHeight: '16px',
                            fontFamily: 'var(--font-mono)',
                            background: `${color}11`,
                            border: `1px solid ${color}33`,
                            color,
                          }}
                        >
                          #{log.id}
                        </Tag>
                        <Tag
                          style={{
                            fontSize: 11,
                            margin: 0,
                            padding: '0 6px',
                            lineHeight: '16px',
                            background: `${color}11`,
                            border: `1px solid ${color}33`,
                            color,
                          }}
                        >
                          {log.action}
                        </Tag>
                        <Text strong style={{ fontSize: 12 }}>
                          {log.actor}
                        </Text>
                        {log.target && (
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            → {log.target}
                          </Text>
                        )}
                      </div>
                      <div className="flex items-center gap-3">
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          {formatDateTime(log.created_at)}
                        </Text>
                        {log.ip && (
                          <Text type="secondary" style={{ fontSize: 11, fontFamily: 'var(--font-mono)' }}>
                            IP {log.ip}
                          </Text>
                        )}
                      </div>
                    </div>
                    <div className="text-right" style={{ minWidth: 120 }}>
                      <Text
                        type="secondary"
                        style={{ fontSize: 10, fontFamily: 'var(--font-mono)' }}
                      >
                        <LinkOutlined /> {log.curr_hash?.slice(0, 16)}...
                      </Text>
                      {log.prev_hash && (
                        <div>
                          <Text
                            type="secondary"
                            style={{ fontSize: 10, fontFamily: 'var(--font-mono)' }}
                          >
                            ← {log.prev_hash?.slice(0, 16)}...
                          </Text>
                        </div>
                      )}
                    </div>
                  </div>
                  {Object.keys(log.metadata).length > 0 && (
                    <pre
                      style={{
                        margin: '8px 0 0',
                        padding: 8,
                        background: 'var(--color-bg)',
                        borderRadius: 4,
                        fontSize: 11,
                        fontFamily: 'var(--font-mono)',
                        color: 'var(--color-mist-dark)',
                        maxHeight: 80,
                        overflow: 'auto',
                      }}
                    >
                      {JSON.stringify(log.metadata, null, 2)}
                    </pre>
                  )}
                </motion.div>
              )
            })}
          </div>
        </Card>
      )}
    </div>
  )
}
