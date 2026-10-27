import { NotificationBell } from '@/components/notification/NotificationBell'
import { useAuthStore } from '@/lib/store/authStore'
import { useUIStore } from '@/lib/store/uiStore'
import { authApi } from '@/lib/api/auth'
import { App, Avatar, Button, Dropdown, Space, Typography } from 'antd'
import {
  BellOutlined,
  CheckOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'motion/react'

const { Text } = Typography

export function TopNav() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const refreshToken = useAuthStore((s) => s.refreshToken)
  const { siderCollapsed, toogleSider } = useUIStore()

  const handleLogout = async () => {
    try {
      if (refreshToken) await authApi.logout(refreshToken)
    } catch {
      // 忽略
    }
    logout()
    message.success('已退出登录')
    navigate('/login')
  }

  const roleLabel = user?.role === 'student' ? '学生' : user?.role === 'teacher' ? '教师' : '管理员'
  const initial = user?.email?.[0]?.toUpperCase() ?? 'U'

  return (
    <header
      className="flex items-center justify-between px-6"
      style={{
        height: 64,
        background: 'var(--color-card)',
        borderBottom: '1px solid var(--color-line)',
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}
    >
      <div className="flex items-center gap-3">
        <Button
          type="text"
          icon={siderCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          onClick={toogleSider}
          aria-label="切换侧边栏"
        />
        <Link to="/" className="flex items-center gap-2 no-underline">
          <motion.div
            initial={{ rotate: -10, opacity: 0 }}
            animate={{ rotate: 0, opacity: 1 }}
            transition={{ type: 'spring', stiffness: 200 }}
            className="flex items-center justify-center"
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              background: 'var(--color-moss)',
              color: 'var(--color-paper)',
              fontFamily: 'var(--font-serif)',
              fontWeight: 700,
              fontSize: 18,
            }}
          >
            L
          </motion.div>
          <div className="hidden sm:block">
            <div
              style={{
                fontFamily: 'var(--font-serif)',
                fontWeight: 600,
                fontSize: 18,
                color: 'var(--color-ink)',
                lineHeight: 1.1,
              }}
            >
              Lumen
            </div>
            <div style={{ fontSize: 11, color: 'var(--color-mist)', letterSpacing: '0.05em' }}>
              LEARNING
            </div>
          </div>
        </Link>
      </div>

      <Space size={16}>
        <NotificationBell />
        <Dropdown
          placement="bottomRight"
          menu={{
            items: [
              {
                key: 'profile',
                icon: <UserOutlined />,
                label: '个人设置',
                onClick: () => navigate('/profile'),
              },
              {
                key: 'notifications',
                icon: <BellOutlined />,
                label: '通知中心',
                onClick: () => navigate('/notifications'),
              },
              { type: 'divider' },
              {
                key: 'logout',
                icon: <CheckOutlined style={{ opacity: 0 }} />,
                danger: true,
                label: '退出登录',
                onClick: handleLogout,
              },
            ],
          }}
        >
          <button
            className="flex items-center gap-2 cursor-pointer"
            style={{
              background: 'transparent',
              border: 'none',
              padding: '4px 8px',
              borderRadius: 8,
            }}
          >
            <Avatar
              size={32}
              style={{ background: 'var(--color-moss)', color: 'var(--color-paper)' }}
            >
              {initial}
            </Avatar>
            <div className="hidden md:block text-left">
              <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--color-ink)', lineHeight: 1.2 }}>
                {user?.email}
              </div>
              <Text type="secondary" style={{ fontSize: 11 }}>
                {roleLabel}
              </Text>
            </div>
          </button>
        </Dropdown>
      </Space>
    </header>
  )
}
