import { useState } from 'react'
import {
  App,
  Button,
  Card,
  Col,
  Form,
  Input,
  Modal,
  Row,
  Skeleton,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { PlusOutlined, TeamOutlined, CopyOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { formatDate } from '@/lib/datetime'
import { motion } from 'motion/react'
import { useNavigate } from 'react-router-dom'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { teacherApi } from '@/lib/api/teacher'
import { useAuthStore } from '@/lib/store/authStore'

const { Text, Paragraph } = Typography

export default function ClassesPage() {
  const { message } = App.useApp()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const [createOpen, setCreateOpen] = useState(false)
  const [createForm] = Form.useForm<{ name: string; description?: string }>()

  const { data: classes, isLoading } = useQuery({
    queryKey: ['teacher', 'classes'],
    queryFn: () => teacherApi.listClasses(),
  })

  const createMutation = useMutation({
    mutationFn: (v: { name: string; description?: string }) => teacherApi.createClass(v),
    onSuccess: (cls) => {
      message.success(`班级 ${cls.name} 已创建，邀请码 ${cls.invite_code}`)
      setCreateOpen(false)
      createForm.resetFields()
      qc.invalidateQueries({ queryKey: ['teacher', 'classes'] })
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        '创建失败'
      message.error(detail)
    },
  })

  const copyCode = (code: string) => {
    navigator.clipboard.writeText(code)
    message.success('邀请码已复制')
  }

  return (
    <div className="max-w-7xl mx-auto">
      <PageHeader
        title="班级管理"
        subtitle={`${user?.role === 'teacher' ? '教师' : '管理员'} · ${classes?.length ?? 0} 个班级 · 学生凭邀请码在学习中心加入`}
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            创建班级
          </Button>
        }
      />

      {isLoading ? (
        <Row gutter={[16, 16]}>
          {[1, 2, 3].map((i) => (
            <Col key={i} xs={24} md={12} lg={8}>
              <Card bordered={false} className="lumen-card">
                <Skeleton active paragraph={{ rows: 3 }} />
              </Card>
            </Col>
          ))}
        </Row>
      ) : !classes || classes.length === 0 ? (
        <EmptyState title="还没有班级" description="创建第一个班级，把邀请码分享给学生" />
      ) : (
        <Row gutter={[16, 16]}>
          {classes.map((cls, idx) => (
            <Col key={cls.id} xs={24} md={12} lg={8}>
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: Math.min(idx * 0.04, 0.3) }}
              >
                <Card
                  bordered={false}
                  hoverable
                  className="lumen-card lumen-card-hover"
                  onClick={() => navigate(`/teacher/classes/${cls.id}`)}
                >
                  <div className="flex items-start justify-between mb-2">
                    <Text
                      strong
                      style={{
                        fontSize: 16,
                        fontFamily: 'var(--font-serif)',
                        color: 'var(--color-ink)',
                      }}
                    >
                      {cls.name}
                    </Text>
                    <Tag
                      color={cls.is_active ? 'success' : 'default'}
                      style={{ fontSize: 10, margin: 0, padding: '0 6px', lineHeight: '16px' }}
                    >
                      {cls.is_active ? '活跃' : '已归档'}
                    </Tag>
                  </div>
                  <Paragraph
                    type="secondary"
                    style={{
                      fontSize: 12,
                      minHeight: 32,
                      marginBottom: 12,
                      lineHeight: 1.6,
                    }}
                    ellipsis={{ rows: 2 }}
                  >
                    {cls.description || '暂无描述'}
                  </Paragraph>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span
                        className="flex items-center gap-1"
                        style={{ fontSize: 12, color: 'var(--color-mist)' }}
                      >
                        <TeamOutlined style={{ fontSize: 11 }} />
                        {cls.member_count} 人
                      </span>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {formatDate(cls.created_at)}
                      </Text>
                    </div>
                    <Tooltip title="复制邀请码">
                      <Tag
                        onClick={(e) => {
                          e.stopPropagation()
                          copyCode(cls.invite_code)
                        }}
                        style={{
                          fontSize: 11,
                          margin: 0,
                          fontFamily: 'var(--font-mono)',
                          cursor: 'pointer',
                          background: 'var(--color-moss-50)',
                          border: '1px solid var(--color-line)',
                          color: 'var(--color-moss)',
                        }}
                      >
                        <CopyOutlined /> {cls.invite_code}
                      </Tag>
                    </Tooltip>
                  </div>
                </Card>
              </motion.div>
            </Col>
          ))}
        </Row>
      )}

      <Modal
        open={createOpen}
        title="创建班级"
        onCancel={() => setCreateOpen(false)}
        onOk={() => createForm.submit()}
        confirmLoading={createMutation.isPending}
        okText="创建"
        cancelText="取消"
      >
        <Form
          form={createForm}
          layout="vertical"
          onFinish={(v) => createMutation.mutate(v)}
          className="mt-4"
        >
          <Form.Item
            name="name"
            label="班级名称"
            rules={[{ required: true, message: '请输入班级名称' }, { max: 60 }]}
          >
            <Input placeholder="如:高三 (1) 班" />
          </Form.Item>
          <Form.Item name="description" label="班级描述" rules={[{ max: 200 }]}>
            <Input.TextArea rows={3} placeholder="可选,简短描述这个班级" maxLength={200} showCount />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
