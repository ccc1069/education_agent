import { Link, useNavigate } from 'react-router-dom'
import { App, Button, Form, Input, Typography } from 'antd'
import { MailOutlined, LockOutlined, UserOutlined } from '@ant-design/icons'
import { motion } from 'motion/react'
import { useMutation } from '@tanstack/react-query'
import { authApi } from '@/lib/api/auth'
import { useAuthStore } from '@/lib/store/authStore'
import type { RegisterRequest } from '@/types/api'

const { Title, Text } = Typography

export default function RegisterPage() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const login = useAuthStore((s) => s.login)
  const [form] = Form.useForm<RegisterRequest & { confirm?: string }>()

  const mutation = useMutation({
    mutationFn: async (payload: RegisterRequest) => {
      const reg = await authApi.register(payload)
      // 注册成功后自动登录
      return authApi.login({ email: payload.email, password: payload.password })
    },
    onSuccess: (data) => {
      login(data.access_token, data.refresh_token, data.user)
      message.success('注册成功,欢迎加入 Lumen Learning')
      navigate('/learn', { replace: true })
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        '注册失败,请稍后重试'
      message.error(detail)
    },
  })

  return (
    <div className="min-h-screen grid lg:grid-cols-2" style={{ background: 'var(--color-paper)' }}>
      {/* 左侧: 表单 */}
      <div className="flex items-center justify-center p-8 lg:p-12 order-2 lg:order-1">
        <motion.div
          initial={{ y: 16, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.4 }}
          className="w-full max-w-sm"
        >
          <Text
            style={{
              fontSize: 12,
              letterSpacing: '0.12em',
              color: 'var(--color-moss)',
              textTransform: 'uppercase',
              fontWeight: 600,
            }}
          >
            注册
          </Text>
          <Title
            level={2}
            style={{ marginTop: 8, marginBottom: 4, color: 'var(--color-ink)' }}
          >
            创建你的账号
          </Title>
          <Text style={{ fontSize: 14, color: 'var(--color-mist-dark)' }}>
            几秒钟开启个性化学习之旅
          </Text>

          <Form
            form={form}
            layout="vertical"
            className="mt-8"
            onFinish={(values) => {
              const { confirm, ...rest } = values
              void confirm
              mutation.mutate(rest)
            }}
            requiredMark={false}
          >
            <Form.Item
              label="姓名(可选)"
              name="name"
              rules={[{ max: 32, message: '姓名最长 32 字符' }]}
            >
              <Input
                size="large"
                prefix={<UserOutlined style={{ color: 'var(--color-mist)' }} />}
                placeholder="如何称呼你"
              />
            </Form.Item>

            <Form.Item
              label="邮箱"
              name="email"
              rules={[
                { required: true, message: '请输入邮箱' },
                { type: 'email', message: '邮箱格式不正确' },
              ]}
            >
              <Input
                size="large"
                prefix={<MailOutlined style={{ color: 'var(--color-mist)' }} />}
                placeholder="you@example.com"
                autoComplete="email"
              />
            </Form.Item>

            <Form.Item
              label="密码"
              name="password"
              rules={[
                { required: true, message: '请输入密码' },
                { min: 8, message: '密码至少 8 位' },
              ]}
            >
              <Input.Password
                size="large"
                prefix={<LockOutlined style={{ color: 'var(--color-mist)' }} />}
                placeholder="至少 8 位"
                autoComplete="new-password"
              />
            </Form.Item>

            <Form.Item
              label="确认密码"
              name="confirm"
              dependencies={['password']}
              rules={[
                { required: true, message: '请再次输入密码' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('password') === value) {
                      return Promise.resolve()
                    }
                    return Promise.reject(new Error('两次密码不一致'))
                  },
                }),
              ]}
            >
              <Input.Password
                size="large"
                prefix={<LockOutlined style={{ color: 'var(--color-mist)' }} />}
                placeholder="再次输入密码"
                autoComplete="new-password"
              />
            </Form.Item>

            <Button
              type="primary"
              htmlType="submit"
              size="large"
              block
              loading={mutation.isPending}
            >
              注册
            </Button>
          </Form>

          <div className="mt-6 text-center">
            <Text style={{ fontSize: 13, color: 'var(--color-mist-dark)' }}>
              已有账号?{' '}
              <Link to="/login" style={{ color: 'var(--color-moss)', fontWeight: 600 }}>
                直接登录
              </Link>
            </Text>
          </div>

          <p
            style={{
              marginTop: 24,
              fontSize: 12,
              lineHeight: 1.6,
              textAlign: 'center',
              color: 'var(--color-mist-dark)',
            }}
          >
            注册即表示同意 Lumen Learning 的服务条款与隐私政策。我们采用 BKT 知识追踪与
            SM-2 间隔重复为你提供个性化学习体验。
          </p>
        </motion.div>
      </div>

      {/* 右侧: 品牌插画 */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.6 }}
        className="hidden lg:flex flex-col justify-between p-12 relative overflow-hidden order-1 lg:order-2"
        style={{
          background:
            'linear-gradient(135deg, #1B4332 0%, #2D5A47 50%, #1B4332 100%)',
          color: 'var(--color-paper)',
        }}
      >
        <div
          aria-hidden
          style={{
            position: 'absolute',
            inset: 0,
            backgroundImage:
              'radial-gradient(circle at 80% 20%, rgba(217, 119, 87, 0.18) 0%, transparent 50%), radial-gradient(circle at 20% 80%, rgba(244, 63, 94, 0.12) 0%, transparent 50%)',
          }}
        />
        <div
          aria-hidden
          style={{
            position: 'absolute',
            inset: 0,
            backgroundImage:
              'linear-gradient(rgba(251, 248, 243, 0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(251, 248, 243, 0.04) 1px, transparent 1px)',
            backgroundSize: '40px 40px',
          }}
        />

        <div className="relative flex items-center justify-end gap-3" style={{ zIndex: 1 }}>
          <div>
            <div
              style={{
                fontFamily: 'var(--font-serif)',
                fontWeight: 600,
                fontSize: 22,
                textAlign: 'right',
                color: '#FBF8F3',
              }}
            >
              Lumen
            </div>
            <div
              style={{
                fontSize: 11,
                letterSpacing: '0.1em',
                textAlign: 'right',
                color: 'rgba(251, 248, 243, 0.7)',
              }}
            >
              LEARNING · EST. 2026
            </div>
          </div>
          <div
            className="flex items-center justify-center"
            style={{
              width: 44,
              height: 44,
              borderRadius: 10,
              background: 'var(--color-paper)',
              color: 'var(--color-moss-dark)',
              fontFamily: 'var(--font-serif)',
              fontWeight: 700,
              fontSize: 24,
            }}
          >
            L
          </div>
        </div>

        <motion.div
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.2, duration: 0.6 }}
          className="relative"
          style={{ zIndex: 1 }}
        >
          <h1
            style={{
              fontFamily: 'var(--font-serif)',
              fontSize: '3.5rem',
              lineHeight: 1.05,
              margin: 0,
              letterSpacing: '-0.02em',
              color: '#FBF8F3',
            }}
          >
            7 个 Agent,
            <br />
            为你而教。
          </h1>
          <p
            style={{
              marginTop: 24,
              marginBottom: 0,
              fontSize: 16,
              lineHeight: 1.7,
              color: 'rgba(251, 248, 243, 0.82)',
              maxWidth: 460,
            }}
          >
            Assessment 评估、Tutor 教学、Curriculum 规划、Hint 提示、Engagement 监测,
            外加 Critic 自反思与 Debate 协商。每一个知识点都由多位 Agent 协同引导。
          </p>

          <div
            className="mt-12 grid grid-cols-2 gap-4"
            style={{ maxWidth: 480 }}
          >
            {[
              { title: 'BKT 知识追踪', desc: 'Beta 分布近似' },
              { title: 'SM-2 间隔重复', desc: '科学复习节奏' },
              { title: 'Vision 多模态', desc: '拍题即获引导' },
              { title: 'RAG 知识库', desc: '教材片段增强' },
            ].map((f) => (
              <div
                key={f.title}
                style={{
                  padding: 16,
                  background: 'rgba(251, 248, 243, 0.08)',
                  border: '1px solid rgba(251, 248, 243, 0.16)',
                  borderRadius: 10,
                }}
              >
                <div
                  style={{
                    fontFamily: 'var(--font-serif)',
                    fontSize: 16,
                    fontWeight: 600,
                    color: '#F5D0A9',
                  }}
                >
                  {f.title}
                </div>
                <div
                  style={{
                    fontSize: 12,
                    marginTop: 2,
                    color: 'rgba(251, 248, 243, 0.72)',
                  }}
                >
                  {f.desc}
                </div>
              </div>
            ))}
          </div>
        </motion.div>

        <div
          className="relative"
          style={{ zIndex: 1, fontSize: 12, color: 'rgba(251, 248, 243, 0.55)' }}
        >
          © 2026 Lumen Learning · 多 Agent 智能教育系统
        </div>
      </motion.div>
    </div>
  )
}
