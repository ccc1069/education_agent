import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { App, Button, Form, Input, Typography } from 'antd'
import { MailOutlined, LockOutlined } from '@ant-design/icons'
import { motion } from 'motion/react'
import { useMutation } from '@tanstack/react-query'
import { authApi } from '@/lib/api/auth'
import { useAuthStore } from '@/lib/store/authStore'
import type { LoginRequest } from '@/types/api'

const { Title, Text } = Typography

export default function LoginPage() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const login = useAuthStore((s) => s.login)
  const [form] = Form.useForm<LoginRequest>()

  const mutation = useMutation({
    mutationFn: (payload: LoginRequest) => authApi.login(payload),
    onSuccess: (data) => {
      login(data.access_token, data.refresh_token, data.user)
      message.success(`欢迎回来,${data.user.email}`)
      const target =
        data.user.role === 'student'
          ? '/learn'
          : data.user.role === 'teacher'
            ? '/teacher/classes'
            : '/admin/audit'
      navigate(target, { replace: true })
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        '登录失败,请检查邮箱和密码'
      message.error(detail)
    },
  })

  const [showDemo, setShowDemo] = useState(false)

  return (
    <div className="min-h-screen grid lg:grid-cols-2" style={{ background: 'var(--color-paper)' }}>
      {/* 左侧: 品牌插画 */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.6 }}
        className="hidden lg:flex flex-col justify-between p-12 relative overflow-hidden"
        style={{
          background:
            'linear-gradient(135deg, #0F2A1F 0%, #1B4332 50%, #2D5A47 100%)',
          color: 'var(--color-paper)',
        }}
      >
        {/* 装饰网格 */}
        <div
          aria-hidden
          style={{
            position: 'absolute',
            inset: 0,
            backgroundImage:
              'radial-gradient(circle at 20% 80%, rgba(217, 119, 87, 0.15) 0%, transparent 50%), radial-gradient(circle at 80% 20%, rgba(16, 185, 129, 0.12) 0%, transparent 50%)',
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

        <div className="relative" style={{ zIndex: 1 }}>
          <div className="flex items-center gap-3">
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
            <div>
              <div
                style={{
                  fontFamily: 'var(--font-serif)',
                  fontWeight: 600,
                  fontSize: 22,
                  color: '#FBF8F3',
                }}
              >
                Lumen
              </div>
              <div
                style={{
                  fontSize: 11,
                  letterSpacing: '0.1em',
                  color: 'rgba(251, 248, 243, 0.7)',
                }}
              >
                LEARNING · EST. 2026
              </div>
            </div>
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
            以光为引,
            <br />
            因材施教。
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
            5-Agent Mesh 架构 · BKT 知识追踪 · SM-2 间隔重复 · LangGraph 多轮教学。
            一个为深度学习而生的智能教育系统。
          </p>

          <div
            className="grid grid-cols-3 gap-4 mt-12"
            style={{ maxWidth: 480 }}
          >
            {[
              { num: '7', label: 'AI Agent' },
              { num: '20+', label: '知识点' },
              { num: '4', label: '模态输入' },
            ].map((s) => (
              <div key={s.label}>
                <div
                  style={{
                    fontFamily: 'var(--font-serif)',
                    fontSize: 32,
                    fontWeight: 600,
                    color: '#F5D0A9',
                  }}
                >
                  {s.num}
                </div>
                <div
                  style={{
                    fontSize: 12,
                    letterSpacing: '0.05em',
                    color: 'rgba(251, 248, 243, 0.72)',
                  }}
                >
                  {s.label}
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

      {/* 右侧: 登录表单 */}
      <div className="flex items-center justify-center p-8 lg:p-12">
        <motion.div
          initial={{ y: 16, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.4, delay: 0.1 }}
          className="w-full max-w-sm"
        >
          <div className="lg:hidden flex items-center gap-3 mb-8">
            <div
              className="flex items-center justify-center"
              style={{
                width: 40,
                height: 40,
                borderRadius: 10,
                background: 'var(--color-moss)',
                color: 'var(--color-paper)',
                fontFamily: 'var(--font-serif)',
                fontWeight: 700,
                fontSize: 22,
              }}
            >
              L
            </div>
            <div style={{ fontFamily: 'var(--font-serif)', fontWeight: 600, fontSize: 22 }}>
              Lumen Learning
            </div>
          </div>

          <Text
            style={{
              fontSize: 12,
              letterSpacing: '0.12em',
              color: 'var(--color-moss)',
              textTransform: 'uppercase',
              fontWeight: 600,
            }}
          >
            登录
          </Text>
          <Title
            level={2}
            style={{ marginTop: 8, marginBottom: 4, color: 'var(--color-ink)' }}
          >
            欢迎回来
          </Title>
          <Text style={{ fontSize: 14, color: 'var(--color-mist-dark)' }}>
            请输入邮箱和密码继续学习
          </Text>

          <Form
            form={form}
            layout="vertical"
            className="mt-8"
            onFinish={(values) => mutation.mutate(values)}
            requiredMark={false}
          >
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
              rules={[{ required: true, message: '请输入密码' }]}
            >
              <Input.Password
                size="large"
                prefix={<LockOutlined style={{ color: 'var(--color-mist)' }} />}
                placeholder="••••••••"
                autoComplete="current-password"
              />
            </Form.Item>

            <Button
              type="primary"
              htmlType="submit"
              size="large"
              block
              loading={mutation.isPending}
              style={{ marginTop: 8 }}
            >
              登录
            </Button>
          </Form>

          <div className="mt-6 text-center">
            <Text style={{ fontSize: 13, color: 'var(--color-mist-dark)' }}>
              还没有账号?{' '}
              <Link
                to="/register"
                style={{ color: 'var(--color-moss)', fontWeight: 600 }}
              >
                立即注册
              </Link>
            </Text>
          </div>

          <div className="mt-12">
            <button
              onClick={() => setShowDemo((v) => !v)}
              className="text-xs cursor-pointer"
              style={{
                color: 'var(--color-mist-dark)',
                background: 'transparent',
                border: 'none',
                padding: 0,
                fontWeight: 500,
              }}
            >
              {showDemo ? '▾' : '▸'} 演示账号
            </button>
            {showDemo && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                className="mt-3 space-y-2"
              >
                {[
                  { role: '学生', email: 'student@demo.com', pwd: 'demo123456' },
                  { role: '教师', email: 'teacher@demo.com', pwd: 'demo123456' },
                  { role: '管理员', email: 'admin@demo.com', pwd: 'demo123456' },
                ].map((acc) => (
                  <button
                    key={acc.email}
                    onClick={() => {
                      form.setFieldsValue({ email: acc.email, password: acc.pwd })
                    }}
                    className="w-full flex items-center justify-between text-left"
                    style={{
                      padding: '8px 12px',
                      background: 'var(--color-card)',
                      border: '1px solid var(--color-line)',
                      borderRadius: 8,
                      cursor: 'pointer',
                    }}
                  >
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--color-ink)' }}>
                        {acc.role}
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--color-mist)' }}>{acc.email}</div>
                    </div>
                    <span style={{ fontSize: 11, color: 'var(--color-moss)' }}>点击填充</span>
                  </button>
                ))}
                <Text style={{ fontSize: 11, display: 'block', marginTop: 8, color: 'var(--color-mist-dark)' }}>
                  真实后端需先执行: python -m scripts.seed_demo_data
                </Text>
              </motion.div>
            )}
          </div>
        </motion.div>
      </div>
    </div>
  )
}
