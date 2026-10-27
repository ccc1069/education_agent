import { useState } from 'react'
import {
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Segmented,
  Select,
  Skeleton,
  Switch,
  Tag,
  Typography,
} from 'antd'
import {
  PlusOutlined,
  DatabaseOutlined,
  CrownOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { formatDateTime } from '@/lib/datetime'
import { motion } from 'motion/react'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { StatCard } from '@/components/ui/StatCard'
import { tenantsApi } from '@/lib/api/tenants'
import type { TenantDetail, TenantPlan, TenantQuotaInfo, TenantSummary } from '@/types/api'

const { Text, Title } = Typography

/** 与后端 TenantQuotaRepository.PLAN_DEFAULTS 保持一致 */
const PLAN_DEFAULTS: Record<
  TenantPlan,
  { max_users: number; max_llm_tokens_per_month: number; blurb: string }
> = {
  free: {
    max_users: 50,
    max_llm_tokens_per_month: 10_000,
    blurb: '小规模试用',
  },
  pro: {
    max_users: 500,
    max_llm_tokens_per_month: 500_000,
    blurb: '中小学常规班级',
  },
  enterprise: {
    max_users: 100_000,
    max_llm_tokens_per_month: 10_000_000,
    blurb: '集团校 / 大规模部署',
  },
}

const PLAN_META: Record<
  TenantPlan,
  { label: string; color: string; icon: React.ReactNode }
> = {
  free: { label: '免费版', color: '#6B7280', icon: <DatabaseOutlined /> },
  pro: { label: '专业版', color: '#3B82F6', icon: <CrownOutlined /> },
  enterprise: { label: '企业版', color: '#D97757', icon: <CrownOutlined /> },
}

function formatTokenQuota(n: number): string {
  if (n >= 10_000) return `${(n / 10_000).toLocaleString('zh-CN')} 万`
  return n.toLocaleString('zh-CN')
}

function usedTokens(quota: TenantQuotaInfo | null | undefined): number {
  if (!quota) return 0
  return quota.current_llm_tokens ?? quota.used_llm_tokens_this_month ?? 0
}

function PlanQuotaHint({ plan }: { plan: TenantPlan }) {
  const d = PLAN_DEFAULTS[plan]
  const meta = PLAN_META[plan]
  return (
    <div
      style={{
        marginTop: 8,
        padding: '10px 12px',
        borderRadius: 8,
        background: `${meta.color}0F`,
        border: `1px solid ${meta.color}33`,
      }}
    >
      <Text strong style={{ fontSize: 13, color: meta.color }}>
        {meta.label}默认配额
      </Text>
      <div style={{ marginTop: 4, fontSize: 12, color: 'var(--color-mist-dark)', lineHeight: 1.6 }}>
        {d.blurb} · 最多 {d.max_users.toLocaleString('zh-CN')} 用户 · 每月{' '}
        {formatTokenQuota(d.max_llm_tokens_per_month)} LLM Token
      </div>
      <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 4 }}>
        创建后可按租户单独改配额；当前仅作档位展示，不会硬拦截调用。
      </Text>
    </div>
  )
}

function PlanCompareTable({ active }: { active?: TenantPlan }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: 8,
        marginBottom: 4,
      }}
    >
      {(Object.keys(PLAN_DEFAULTS) as TenantPlan[]).map((p) => {
        const d = PLAN_DEFAULTS[p]
        const meta = PLAN_META[p]
        const selected = active === p
        return (
          <div
            key={p}
            style={{
              padding: 10,
              borderRadius: 8,
              border: selected ? `1.5px solid ${meta.color}` : '1px solid var(--color-line)',
              background: selected ? `${meta.color}0A` : 'var(--color-paper)',
            }}
          >
            <div style={{ fontSize: 12, fontWeight: 600, color: meta.color, marginBottom: 4 }}>
              {meta.label}
            </div>
            <div style={{ fontSize: 11, color: 'var(--color-mist-dark)', lineHeight: 1.55 }}>
              <div>{d.max_users.toLocaleString('zh-CN')} 用户</div>
              <div>{formatTokenQuota(d.max_llm_tokens_per_month)} token/月</div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default function TenantsPage() {
  const { message, modal } = App.useApp()
  const qc = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<TenantDetail | null>(null)
  const [createForm] = Form.useForm<{
    name: string
    slug: string
    plan: TenantPlan
  }>()
  const [editForm] = Form.useForm<{
    name: string
    plan: TenantPlan
    is_active: boolean
    max_users: number
    max_llm_tokens_per_month: number
  }>()
  const createPlan = Form.useWatch('plan', createForm) as TenantPlan | undefined
  const editPlan = Form.useWatch('plan', editForm) as TenantPlan | undefined

  const { data: tenants, isLoading } = useQuery({
    queryKey: ['tenants'],
    queryFn: () => tenantsApi.list({ limit: 100 }),
  })

  const createMutation = useMutation({
    mutationFn: (v: { name: string; slug: string; plan: TenantPlan }) =>
      tenantsApi.create({ ...v, plan: v.plan }),
    onSuccess: () => {
      message.success('租户已创建')
      setCreateOpen(false)
      createForm.resetFields()
      qc.invalidateQueries({ queryKey: ['tenants'] })
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        '创建失败'
      message.error(detail)
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: number
      payload: Partial<{ name: string; plan: TenantPlan; is_active: boolean }>
    }) => tenantsApi.update(id, payload),
    onSuccess: () => {
      message.success('租户已更新')
      qc.invalidateQueries({ queryKey: ['tenants'] })
    },
  })

  const quotaMutation = useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: number
      payload: { max_users?: number; max_llm_tokens_per_month?: number }
    }) => tenantsApi.updateQuota(id, payload),
    onSuccess: () => {
      message.success('配额已更新')
      qc.invalidateQueries({ queryKey: ['tenants'] })
    },
  })

  const resetQuotaMutation = useMutation({
    mutationFn: (id: number) => tenantsApi.resetQuota(id),
    onSuccess: async () => {
      message.success('当月用量已重置')
      if (editTarget) {
        const detail = await tenantsApi.get(editTarget.id)
        setEditTarget(detail)
      }
      qc.invalidateQueries({ queryKey: ['tenants'] })
    },
  })

  const removeMutation = useMutation({
    mutationFn: (id: number) => tenantsApi.remove(id),
    onSuccess: () => {
      message.success('租户已禁用')
      setEditTarget(null)
      qc.invalidateQueries({ queryKey: ['tenants'] })
    },
  })

  const handleEdit = async (t: TenantSummary) => {
    const detail = await tenantsApi.get(t.id)
    setEditTarget(detail)
    editForm.setFieldsValue({
      name: detail.name,
      plan: detail.plan,
      is_active: detail.is_active,
      max_users: detail.quota.max_users,
      max_llm_tokens_per_month: detail.quota.max_llm_tokens_per_month,
    })
  }

  const handleDisable = (t: TenantDetail) => {
    modal.confirm({
      title: '确认禁用租户?',
      content: `"${t.name}" 将被停用（软禁用，数据保留，可稍后重新启用）。`,
      okText: '禁用',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => removeMutation.mutate(t.id),
    })
  }

  const applyPlanDefaults = (plan: TenantPlan) => {
    const d = PLAN_DEFAULTS[plan]
    editForm.setFieldsValue({
      max_users: d.max_users,
      max_llm_tokens_per_month: d.max_llm_tokens_per_month,
    })
  }

  const totalUsers = tenants?.reduce((s, t) => s + (t.user_count ?? 0), 0) ?? 0
  const activeCount = tenants?.filter((t) => t.is_active).length ?? 0
  const enterpriseCount = tenants?.filter((t) => t.plan === 'enterprise').length ?? 0
  const proCount = tenants?.filter((t) => t.plan === 'pro').length ?? 0

  return (
    <div className="max-w-7xl mx-auto">
      <PageHeader
        title="租户管理"
        subtitle="多租户隔离 · 方案配额档位（展示与配置）"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            新建租户
          </Button>
        }
      />

      <Card bordered={false} className="lumen-card mb-4" size="small">
        <Text strong style={{ fontSize: 13, display: 'block', marginBottom: 8 }}>
          订阅方案对比
        </Text>
        <PlanCompareTable />
        <Text type="secondary" style={{ fontSize: 11 }}>
          与后端默认配额一致：免费 50 人 / 1 万 token，专业 500 人 / 50 万 token，企业 10 万人 / 1000
          万 token。
        </Text>
      </Card>

      <Row gutter={[16, 16]} className="mb-6">
        <Col xs={12} md={6}>
          <StatCard title="租户总数" value={tenants?.length ?? 0} loading={isLoading} />
        </Col>
        <Col xs={12} md={6}>
          <StatCard
            title="活跃租户"
            value={activeCount}
            valueStyle={{ color: 'var(--color-moss)' }}
            loading={isLoading}
          />
        </Col>
        <Col xs={12} md={6}>
          <StatCard
            title="专业 / 企业"
            value={`${proCount} / ${enterpriseCount}`}
            valueStyle={{ color: '#D97757', fontSize: 22 }}
            loading={isLoading}
          />
        </Col>
        <Col xs={12} md={6}>
          <StatCard
            title="总用户数"
            value={totalUsers}
            valueStyle={{ color: '#3B82F6' }}
            loading={isLoading}
          />
        </Col>
      </Row>

      {isLoading ? (
        <Card bordered={false} className="lumen-card">
          <Skeleton active paragraph={{ rows: 6 }} />
        </Card>
      ) : !tenants || tenants.length === 0 ? (
        <EmptyState title="暂无租户" description="创建第一个租户开始多租户管理" />
      ) : (
        <Row gutter={[16, 16]}>
          {tenants.map((t, idx) => {
            const plan = PLAN_META[t.plan]
            const defaults = PLAN_DEFAULTS[t.plan]
            const maxUsers = t.quota?.max_users ?? defaults.max_users
            const maxTokens =
              t.quota?.max_llm_tokens_per_month ?? defaults.max_llm_tokens_per_month
            const used = usedTokens(t.quota)
            return (
              <Col key={t.id} xs={24} md={12} lg={8}>
                <motion.div
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(idx * 0.03, 0.3) }}
                >
                  <Card
                    bordered={false}
                    hoverable
                    className="lumen-card lumen-card-hover"
                    onClick={() => handleEdit(t)}
                  >
                    <div className="flex items-start justify-between mb-2">
                      <Text
                        strong
                        style={{
                          fontSize: 15,
                          fontFamily: 'var(--font-serif)',
                          color: 'var(--color-ink)',
                        }}
                      >
                        {t.name}
                      </Text>
                      <Tag
                        style={{
                          fontSize: 10,
                          margin: 0,
                          padding: '0 6px',
                          lineHeight: '16px',
                          background: `${plan.color}11`,
                          border: `1px solid ${plan.color}33`,
                          color: plan.color,
                        }}
                      >
                        {plan.icon} {plan.label}
                      </Tag>
                    </div>
                    <Text
                      type="secondary"
                      style={{ fontSize: 11, fontFamily: 'var(--font-mono)', display: 'block' }}
                    >
                      {t.slug}
                    </Text>
                    <div
                      style={{
                        marginTop: 10,
                        fontSize: 12,
                        color: 'var(--color-mist-dark)',
                        lineHeight: 1.55,
                      }}
                    >
                      <div>
                        用户 {t.user_count ?? 0} / {maxUsers.toLocaleString('zh-CN')}
                      </div>
                      <div>
                        Token {used.toLocaleString('zh-CN')} / {formatTokenQuota(maxTokens)}
                        /月
                      </div>
                    </div>
                    <div className="flex items-center justify-between mt-2">
                      <Tag
                        color={t.is_active ? 'success' : 'default'}
                        style={{ fontSize: 10, margin: 0, padding: '0 6px', lineHeight: '16px' }}
                      >
                        {t.is_active ? '活跃' : '停用'}
                      </Tag>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {defaults.blurb}
                      </Text>
                    </div>
                  </Card>
                </motion.div>
              </Col>
            )
          })}
        </Row>
      )}

      <Modal
        open={createOpen}
        title="新建租户"
        onCancel={() => setCreateOpen(false)}
        onOk={() => createForm.submit()}
        confirmLoading={createMutation.isPending}
        okText="创建"
        cancelText="取消"
        width={560}
      >
        <Form
          form={createForm}
          layout="vertical"
          onFinish={(v) => createMutation.mutate(v)}
          className="mt-4"
          initialValues={{ plan: 'free' }}
        >
          <Form.Item
            name="name"
            label="租户名称"
            rules={[{ required: true, message: '请输入名称' }, { max: 60 }]}
          >
            <Input placeholder="如:示范学校" />
          </Form.Item>
          <Form.Item
            name="slug"
            label="租户标识"
            rules={[
              { required: true, message: '请输入标识' },
              { pattern: /^[a-z0-9-]+$/, message: '仅允许小写字母、数字、连字符' },
            ]}
          >
            <Input placeholder="如:demo-school" />
          </Form.Item>
          <Form.Item name="plan" label="订阅方案" style={{ marginBottom: 8 }}>
            <Segmented
              block
              options={[
                { label: '免费版', value: 'free' },
                { label: '专业版', value: 'pro' },
                { label: '企业版', value: 'enterprise' },
              ]}
            />
          </Form.Item>
          <PlanCompareTable active={createPlan ?? 'free'} />
          <PlanQuotaHint plan={createPlan ?? 'free'} />
        </Form>
      </Modal>

      <Modal
        open={!!editTarget}
        title={editTarget && `编辑租户 · ${editTarget.name}`}
        onCancel={() => setEditTarget(null)}
        footer={
          <div className="flex justify-between">
            <Button
              danger
              onClick={() => editTarget && handleDisable(editTarget)}
              loading={removeMutation.isPending}
            >
              禁用租户
            </Button>
            <div>
              <Button onClick={() => setEditTarget(null)}>取消</Button>
              <Button
                type="primary"
                onClick={async () => {
                  if (!editTarget) return
                  const v = editForm.getFieldsValue()
                  await updateMutation.mutateAsync({
                    id: editTarget.id,
                    payload: {
                      name: v.name,
                      plan: v.plan,
                      is_active: v.is_active,
                    },
                  })
                  await quotaMutation.mutateAsync({
                    id: editTarget.id,
                    payload: {
                      max_users: v.max_users,
                      max_llm_tokens_per_month: v.max_llm_tokens_per_month,
                    },
                  })
                  const detail = await tenantsApi.get(editTarget.id)
                  setEditTarget(detail)
                  editForm.setFieldsValue({
                    max_users: detail.quota.max_users,
                    max_llm_tokens_per_month: detail.quota.max_llm_tokens_per_month,
                    plan: detail.plan,
                    is_active: detail.is_active,
                    name: detail.name,
                  })
                }}
                loading={updateMutation.isPending || quotaMutation.isPending}
              >
                保存
              </Button>
            </div>
          </div>
        }
        width={680}
      >
        {editTarget && (
          <div>
            <Form form={editForm} layout="vertical" className="mt-4">
              <Form.Item name="name" label="租户名称" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Row gutter={12}>
                <Col xs={24} md={12}>
                  <Form.Item name="plan" label="订阅方案">
                    <Select
                      options={[
                        { value: 'free', label: '免费版' },
                        { value: 'pro', label: '专业版' },
                        { value: 'enterprise', label: '企业版' },
                      ]}
                      onChange={(p: TenantPlan) => applyPlanDefaults(p)}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item name="is_active" label="启用状态" valuePropName="checked">
                    <Switch checkedChildren="启用" unCheckedChildren="停用" />
                  </Form.Item>
                </Col>
              </Row>
              <PlanQuotaHint plan={editPlan ?? editTarget.plan} />

              <Title level={5} style={{ marginTop: 16 }}>
                配额控制
              </Title>
              <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>
                切换方案会填入该档默认值，仍可手工改。
              </Text>
              <Row gutter={12}>
                <Col xs={24} md={12}>
                  <Form.Item name="max_users" label="最大用户数">
                    <InputNumber min={1} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item name="max_llm_tokens_per_month" label="月度 LLM Token 上限">
                    <InputNumber min={0} step={10000} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
              </Row>
            </Form>

            <Card bordered={false} size="small" style={{ background: 'var(--color-paper)' }}>
              <Descriptions column={1} size="small">
                <Descriptions.Item label="当月 Token 用量">
                  <Text
                    strong
                    style={{
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--color-moss)',
                    }}
                  >
                    {usedTokens(editTarget.quota).toLocaleString('zh-CN')}
                  </Text>{' '}
                  / {editTarget.quota.max_llm_tokens_per_month.toLocaleString('zh-CN')}
                </Descriptions.Item>
                <Descriptions.Item label="使用率">
                  {editTarget.quota.max_llm_tokens_per_month > 0
                    ? `${((usedTokens(editTarget.quota) / editTarget.quota.max_llm_tokens_per_month) * 100).toFixed(1)}%`
                    : '-'}
                </Descriptions.Item>
                <Descriptions.Item label="当前用户">
                  {editTarget.user_count} / {editTarget.quota.max_users}
                </Descriptions.Item>
                <Descriptions.Item label="创建时间">
                  {formatDateTime(editTarget.created_at, 'YYYY-MM-DD HH:mm')}
                </Descriptions.Item>
              </Descriptions>
              <Button
                size="small"
                icon={<ReloadOutlined />}
                onClick={() => resetQuotaMutation.mutate(editTarget.id)}
                loading={resetQuotaMutation.isPending}
                className="mt-2"
              >
                重置当月用量
              </Button>
            </Card>
          </div>
        )}
      </Modal>
    </div>
  )
}
