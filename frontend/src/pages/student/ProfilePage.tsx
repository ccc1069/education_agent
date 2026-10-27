import { useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Form,
  Input,
  Modal,
  Row,
  Select,
  Skeleton,
  Switch,
  Tag,
  Typography,
} from 'antd'
import { DownloadOutlined, ExclamationCircleOutlined, ExportOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { formatDateTime, diffFromNow } from '@/lib/datetime'
import { PageHeader } from '@/components/ui/PageHeader'
import { notificationsApi } from '@/lib/api/notifications'
import { privacyApi } from '@/lib/api/privacy'
import { useAuthStore } from '@/lib/store/authStore'
import type { ConsentType } from '@/types/api'

const { Text, Title, Paragraph } = Typography

const CONSENT_ITEMS: {
  key: ConsentType
  label: string
  desc: string
  comingSoon?: boolean
}[] = [
  { key: 'analytics', label: '学习行为分析', desc: '用于改进学习路径推荐和 Agent 策略' },
  { key: 'llm_training', label: 'LLM 训练', desc: '允许将匿名化对话用于模型微调(默认关闭)' },
  {
    key: 'marketing',
    label: '产品营销',
    desc: '接收产品更新和优惠信息',
    comingSoon: true,
  },
  {
    key: 'third_party_share',
    label: '第三方共享',
    desc: '与合作伙伴共享学习数据(默认关闭)',
    comingSoon: true,
  },
]

const HOUR_OPTIONS = Array.from({ length: 24 }, (_, h) => ({
  value: h,
  label: `${String(h).padStart(2, '0')}:00`,
}))

export default function ProfilePage() {
  const { message, modal } = App.useApp()
  const qc = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const [deleteForm] = Form.useForm<{ reason: string }>()

  const { data: consent, isLoading: consentLoading } = useQuery({
    queryKey: ['consent'],
    queryFn: () => privacyApi.getConsent(),
  })

  const { data: preferences, isLoading: prefLoading } = useQuery({
    queryKey: ['notification-preferences'],
    queryFn: () => notificationsApi.getPreferences(),
  })

  const { data: exportJobs } = useQuery({
    queryKey: ['export-jobs'],
    queryFn: () => privacyApi.listExportJobs(),
  })

  const { data: deletionRequest } = useQuery({
    queryKey: ['deletion-request'],
    queryFn: () => privacyApi.getDeletionRequest(),
  })

  const consentMutation = useMutation({
    mutationFn: ({ type, granted }: { type: ConsentType; granted: boolean }) =>
      privacyApi.updateConsent(type, granted),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['consent'] })
      message.success('同意偏好已更新')
    },
  })

  const prefMutation = useMutation({
    mutationFn: (payload: Parameters<typeof notificationsApi.updatePreferences>[0]) =>
      notificationsApi.updatePreferences(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notification-preferences'] })
      message.success('通知偏好已保存')
    },
  })

  const exportMutation = useMutation({
    mutationFn: () => privacyApi.requestExport(),
    onSuccess: async (job) => {
      await qc.invalidateQueries({ queryKey: ['export-jobs'] })
      if (job.status === 'completed' && job.id) {
        try {
          await privacyApi.downloadExport(job.id)
          message.success('数据已导出并开始下载')
          return
        } catch {
          message.warning('导出已完成,请点击列表中的下载按钮')
          return
        }
      }
      message.success('已发起数据导出,完成后可在列表中下载')
    },
    onError: () => {
      message.error('导出失败,请稍后重试')
    },
  })

  const handleDownloadExport = async (jobId: number) => {
    try {
      await privacyApi.downloadExport(jobId)
      message.success('已开始下载')
    } catch {
      message.error('下载失败')
    }
  }

  const deleteMutation = useMutation({
    mutationFn: (reason: string) => privacyApi.requestDeletion(reason),
    onSuccess: () => {
      message.success('已提交删除请求,30 天后执行')
      qc.invalidateQueries({ queryKey: ['deletion-request'] })
    },
  })

  const cancelDeleteMutation = useMutation({
    mutationFn: () => privacyApi.cancelDeletion(),
    onSuccess: () => {
      message.success('删除请求已取消')
      qc.invalidateQueries({ queryKey: ['deletion-request'] })
    },
  })

  const handleDelete = () => {
    modal.confirm({
      title: '确认删除账号?',
      icon: <ExclamationCircleOutlined style={{ color: '#F43F5E' }} />,
      content: (
        <div>
          <Paragraph type="danger" style={{ marginTop: 8 }}>
            这将启动 30 天倒计时,到期后所有数据将被永久删除。
          </Paragraph>
          <Form form={deleteForm} layout="vertical">
            <Form.Item
              name="reason"
              label="删除原因(可选)"
              rules={[{ max: 200 }]}
            >
              <Input.TextArea
                rows={3}
                placeholder="告诉我们为什么离开,帮助我们改进..."
                maxLength={200}
                showCount
              />
            </Form.Item>
          </Form>
        </div>
      ),
      okText: '确认删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        const values = await deleteForm.validateFields().catch(() => ({ reason: '' }))
        deleteMutation.mutate(values.reason ?? '')
      },
    })
  }

  return (
    <div className="max-w-4xl mx-auto">
      <PageHeader title="个人设置" subtitle="隐私同意 · 通知偏好 · 数据导出 · 账号删除" />

      {deletionRequest && (
        <Alert
          type="warning"
          showIcon
          className="mb-4"
          message="账号删除请求进行中"
          description={
            <div className="flex items-center justify-between">
              <Text style={{ fontSize: 13 }}>
                将于 {formatDateTime(deletionRequest.scheduled_at, 'YYYY-MM-DD HH:mm')} 执行
                (剩 {Math.max(0, diffFromNow(deletionRequest.scheduled_at, 'day'))} 天)
              </Text>
              <Button
                size="small"
                danger
                onClick={() => cancelDeleteMutation.mutate()}
                loading={cancelDeleteMutation.isPending}
              >
                取消删除
              </Button>
            </div>
          }
        />
      )}

      <Row gutter={[16, 16]}>
        {/* 个人信息 */}
        <Col xs={24}>
          <Card bordered={false} className="lumen-card">
            <Title level={5} style={{ marginTop: 0 }}>
              账号信息
            </Title>
            <Row gutter={[16, 12]}>
              <Col xs={12} md={6}>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  邮箱
                </Text>
                <div style={{ fontSize: 14, fontWeight: 500 }}>{user?.email}</div>
              </Col>
              <Col xs={12} md={6}>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  角色
                </Text>
                <div>
                  <Tag
                    color="default"
                    style={{
                      background: 'var(--color-moss-50)',
                      color: 'var(--color-moss)',
                      border: '1px solid var(--color-line)',
                    }}
                  >
                    {user?.role === 'student' ? '学生' : user?.role === 'teacher' ? '教师' : '管理员'}
                  </Tag>
                </div>
              </Col>
              <Col xs={12} md={6}>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  学习者 ID
                </Text>
                <div
                  className="lumen-mono"
                  style={{ fontSize: 13, color: 'var(--color-mist-dark)' }}
                >
                  {user?.learner_id ?? '—'}
                </div>
              </Col>
              <Col xs={12} md={6}>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  用户 ID
                </Text>
                <div
                  className="lumen-mono"
                  style={{ fontSize: 13, color: 'var(--color-mist-dark)' }}
                >
                  #{user?.id}
                </div>
              </Col>
            </Row>
          </Card>
        </Col>

        {/* 隐私同意 */}
        <Col xs={24}>
          <Card bordered={false} className="lumen-card">
            <Title level={5} style={{ marginTop: 0 }}>
              隐私同意偏好
            </Title>
            <Text type="secondary" style={{ fontSize: 12 }}>
              根据《个人信息保护法》和 GDPR,你随时可以调整数据使用授权
            </Text>
            {consentLoading ? (
              <Skeleton active className="mt-4" />
            ) : (
              <div className="mt-4 space-y-3">
                {CONSENT_ITEMS.map((item) => (
                  <div
                    key={item.key}
                    className="flex items-center justify-between"
                    style={{
                      padding: 12,
                      background: 'var(--color-paper)',
                      borderRadius: 8,
                      border: '1px solid var(--color-line)',
                    }}
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <Text strong style={{ fontSize: 13 }}>
                          {item.label}
                        </Text>
                        {item.comingSoon && (
                          <Tag
                            style={{
                              margin: 0,
                              fontSize: 10,
                              lineHeight: '18px',
                              padding: '0 6px',
                              borderColor: 'var(--color-line)',
                              color: 'var(--color-mist)',
                              background: 'transparent',
                            }}
                          >
                            即将支持
                          </Tag>
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--color-mist)' }}>{item.desc}</div>
                    </div>
                    <Switch
                      checked={consent?.[item.key] ?? false}
                      onChange={(checked) =>
                        consentMutation.mutate({ type: item.key, granted: checked })
                      }
                      loading={consentMutation.isPending}
                    />
                  </div>
                ))}
              </div>
            )}
          </Card>
        </Col>

        {/* 通知偏好 */}
        <Col xs={24}>
          <Card bordered={false} className="lumen-card">
            <Title level={5} style={{ marginTop: 0 }}>
              通知偏好
            </Title>
            {prefLoading ? (
              <Skeleton active />
            ) : preferences ? (
              <Row gutter={[16, 12]}>
                <Col xs={24} md={8}>
                  <PrefSwitch
                    label="WebSocket 推送"
                    desc="在线时实时推送"
                    checked={preferences.ws_enabled}
                    onChange={(v) => prefMutation.mutate({ ws_enabled: v })}
                  />
                </Col>
                <Col xs={24} md={8}>
                  <PrefSwitch
                    label="邮件推送"
                    desc="重要事件邮件通知"
                    comingSoon
                    checked={preferences.email_enabled}
                    onChange={(v) => prefMutation.mutate({ email_enabled: v })}
                  />
                </Col>
                <Col xs={24} md={8}>
                  <PrefSwitch
                    label="APP 推送"
                    desc="移动端推送通知"
                    comingSoon
                    checked={preferences.push_enabled}
                    onChange={(v) => prefMutation.mutate({ push_enabled: v })}
                  />
                </Col>
                <Col xs={24} md={12}>
                  <div
                    style={{
                      padding: 12,
                      background: 'var(--color-paper)',
                      borderRadius: 8,
                      border: '1px solid var(--color-line)',
                    }}
                  >
                    <Text strong style={{ fontSize: 13 }}>
                      勿扰时段
                    </Text>
                    <div className="mt-2 flex items-center gap-2">
                      <Select
                        style={{ width: 100 }}
                        allowClear
                        placeholder="开始"
                        value={preferences.quiet_hours_start ?? undefined}
                        options={HOUR_OPTIONS}
                        onChange={(v) =>
                          prefMutation.mutate({ quiet_hours_start: v ?? null })
                        }
                      />
                      <Text type="secondary">至</Text>
                      <Select
                        style={{ width: 100 }}
                        allowClear
                        placeholder="结束"
                        value={preferences.quiet_hours_end ?? undefined}
                        options={HOUR_OPTIONS}
                        onChange={(v) =>
                          prefMutation.mutate({ quiet_hours_end: v ?? null })
                        }
                      />
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        北京时间
                      </Text>
                    </div>
                  </div>
                </Col>
                <Col xs={24} md={12}>
                  <div
                    style={{
                      padding: 12,
                      background: 'var(--color-paper)',
                      borderRadius: 8,
                      border: '1px solid var(--color-line)',
                    }}
                  >
                    <Text strong style={{ fontSize: 13 }}>
                      最低推送优先级
                    </Text>
                    <div className="mt-2">
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        仅推送优先级 ≥ 此值的通知(0 低 / 1 中 / 2 高)
                      </Text>
                      <div className="mt-1 flex gap-2">
                        {[0, 1, 2].map((p) => (
                          <Button
                            key={p}
                            size="small"
                            type={preferences.min_priority === p ? 'primary' : 'default'}
                            onClick={() => prefMutation.mutate({ min_priority: p })}
                          >
                            {p === 0 ? '全部' : p === 1 ? '中+' : '仅高'}
                          </Button>
                        ))}
                      </div>
                    </div>
                  </div>
                </Col>
              </Row>
            ) : null}
          </Card>
        </Col>

        {/* 数据导出 */}
        <Col xs={24}>
          <Card bordered={false} className="lumen-card">
            <Title level={5} style={{ marginTop: 0 }}>
              数据导出
            </Title>
            <Text type="secondary" style={{ fontSize: 12 }}>
              导出你的全部学习数据(包括答题历史、知识掌握度、Agent 交互记录)
            </Text>
            <Button
              type="primary"
              className="mt-3"
              icon={<ExportOutlined />}
              loading={exportMutation.isPending}
              onClick={() => exportMutation.mutate()}
            >
              申请数据导出
            </Button>
            {exportJobs && exportJobs.length > 0 && (
              <div className="mt-4 space-y-2">
                <Text type="secondary" style={{ fontSize: 11, letterSpacing: '0.05em' }}>
                  历史导出
                </Text>
                {exportJobs.map((job) => (
                  <div
                    key={job.id}
                    className="flex items-center justify-between"
                    style={{
                      padding: 8,
                      background: 'var(--color-paper)',
                      borderRadius: 6,
                      border: '1px solid var(--color-line)',
                    }}
                  >
                    <div>
                      <Text style={{ fontSize: 13 }}>
                        导出 #{job.id} · {job.status}
                      </Text>
                      <div style={{ fontSize: 11, color: 'var(--color-mist)' }}>
                        {formatDateTime(job.requested_at, 'YYYY-MM-DD HH:mm')}
                        {job.file_size_bytes && ` · ${(job.file_size_bytes / 1024).toFixed(1)} KB`}
                      </div>
                    </div>
                    {(job.download_url || job.status === 'completed') && (
                      <Button
                        size="small"
                        icon={<DownloadOutlined />}
                        onClick={() => handleDownloadExport(job.id)}
                      >
                        下载
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Card>
        </Col>

        {/* 账号删除 */}
        <Col xs={24}>
          <Card
            bordered={false}
            style={{
              borderColor: '#F43F5E',
              border: '1px solid rgba(244, 63, 94, 0.3)',
            }}
          >
            <Title level={5} style={{ marginTop: 0, color: '#F43F5E' }}>
              危险操作
            </Title>
            <Paragraph type="secondary" style={{ fontSize: 12 }}>
              删除账号将启动 30 天倒计时,期间可取消。到期后所有数据将被永久删除且不可恢复。
            </Paragraph>
            <Button
              danger
              icon={<ExclamationCircleOutlined />}
              onClick={handleDelete}
              loading={deleteMutation.isPending}
              disabled={!!deletionRequest}
            >
              {deletionRequest ? '删除请求已存在' : '申请删除账号'}
            </Button>
          </Card>
        </Col>
      </Row>
    </div>
  )
}

function PrefSwitch({
  label,
  desc,
  checked,
  onChange,
  comingSoon,
}: {
  label: string
  desc: string
  checked: boolean
  onChange: (v: boolean) => void
  comingSoon?: boolean
}) {
  return (
    <div
      className="flex items-center justify-between"
      style={{
        padding: 12,
        background: 'var(--color-paper)',
        borderRadius: 8,
        border: '1px solid var(--color-line)',
      }}
    >
      <div>
        <div className="flex items-center gap-2">
          <Text strong style={{ fontSize: 13 }}>
            {label}
          </Text>
          {comingSoon && (
            <Tag
              style={{
                margin: 0,
                fontSize: 10,
                lineHeight: '18px',
                padding: '0 6px',
                borderColor: 'var(--color-line)',
                color: 'var(--color-mist)',
                background: 'transparent',
              }}
            >
              即将支持
            </Tag>
          )}
        </div>
        <div style={{ fontSize: 11, color: 'var(--color-mist)' }}>{desc}</div>
      </div>
      <Switch checked={checked} onChange={onChange} />
    </div>
  )
}
