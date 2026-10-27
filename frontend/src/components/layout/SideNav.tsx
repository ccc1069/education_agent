import { Layout, Menu } from 'antd'
import {
  AppstoreOutlined,
  AuditOutlined,
  BellOutlined,
  BookOutlined,
  BulbOutlined,
  CameraOutlined,
  ClusterOutlined,
  DashboardOutlined,
  FileTextOutlined,
  FundProjectionScreenOutlined,
  ScheduleOutlined,
  SettingOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import { useLocation, useNavigate } from 'react-router-dom'
import type { Role } from '@/types/user'
import { useAuthStore } from '@/lib/store/authStore'
import { useUIStore } from '@/lib/store/uiStore'
import type { MenuProps } from 'antd'

const { Sider } = Layout

type MenuItem = Required<MenuProps>['items'][number]

interface NavItem {
  key: string
  label: string
  icon: React.ReactNode
  roles: Role[]
}

const STUDENT_NAV: NavItem[] = [
  { key: '/learn', label: '学习中心', icon: <BookOutlined />, roles: ['student', 'teacher', 'admin'] },
  { key: '/assignments', label: '我的作业', icon: <ScheduleOutlined />, roles: ['student'] },
  { key: '/practice', label: '练习题库', icon: <AppstoreOutlined />, roles: ['student', 'teacher', 'admin'] },
  { key: '/vision', label: '拍题分析', icon: <CameraOutlined />, roles: ['student', 'teacher', 'admin'] },
  { key: '/progress', label: '学习进度', icon: <FundProjectionScreenOutlined />, roles: ['student', 'teacher', 'admin'] },
  { key: '/knowledge-graph', label: '知识图谱', icon: <ClusterOutlined />, roles: ['student', 'teacher', 'admin'] },
  { key: '/notifications', label: '通知中心', icon: <BellOutlined />, roles: ['student', 'teacher', 'admin'] },
  { key: '/profile', label: '个人设置', icon: <SettingOutlined />, roles: ['student', 'teacher', 'admin'] },
]

const TEACHER_NAV: NavItem[] = [
  { key: '/teacher/classes', label: '班级管理', icon: <TeamOutlined />, roles: ['teacher', 'admin'] },
  { key: '/teacher/assignments', label: '作业管理', icon: <ScheduleOutlined />, roles: ['teacher', 'admin'] },
  { key: '/teacher/questions', label: '题库管理', icon: <FileTextOutlined />, roles: ['teacher', 'admin'] },
  { key: '/teacher/knowledge-base', label: '知识库', icon: <BookOutlined />, roles: ['teacher', 'admin'] },
]

const ADMIN_NAV: NavItem[] = [
  { key: '/admin/tenants', label: '租户管理', icon: <DashboardOutlined />, roles: ['admin'] },
  { key: '/admin/audit', label: '审计日志', icon: <AuditOutlined />, roles: ['admin'] },
  { key: '/admin/tasks', label: '任务调度', icon: <BulbOutlined />, roles: ['admin'] },
]

function buildMenuItems(role: Role): { label: string; key: string; children: MenuItem[] }[] {
  const filterByRole = (items: NavItem[]) =>
    items.filter((item) => item.roles.includes(role))

  const studentItems = filterByRole(STUDENT_NAV).map((item) => ({
    key: item.key,
    icon: item.icon,
    label: item.label,
  }))
  const teacherItems = filterByRole(TEACHER_NAV).map((item) => ({
    key: item.key,
    icon: item.icon,
    label: item.label,
  }))
  const adminItems = filterByRole(ADMIN_NAV).map((item) => ({
    key: item.key,
    icon: item.icon,
    label: item.label,
  }))

  const groups: { label: string; key: string; children: MenuItem[] }[] = []
  if (studentItems.length) {
    groups.push({ label: '学习', key: 'student', children: studentItems })
  }
  if (role === 'teacher' || role === 'admin') {
    if (teacherItems.length) groups.push({ label: '教学', key: 'teacher', children: teacherItems })
  }
  if (role === 'admin' && adminItems.length) {
    groups.push({ label: '管理', key: 'admin', children: adminItems })
  }
  return groups
}

export function SideNav() {
  const location = useLocation()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const { siderCollapsed } = useUIStore()

  if (!user) return null

  const groups = buildMenuItems(user.role)
  const items: MenuItem[] = groups.map((group) => ({
    type: 'group',
    label: group.label,
    key: group.key,
    children: group.children,
  }))

  const selectedKey =
    '/' +
    location.pathname
      .split('/')
      .filter(Boolean)
      .slice(0, 2)
      .join('/')

  return (
    <Sider
      width={240}
      collapsedWidth={72}
      collapsible
      collapsed={siderCollapsed}
      trigger={null}
      theme="light"
      style={{
        background: 'var(--color-card)',
        borderRight: '1px solid var(--color-line)',
        height: 'calc(100vh - 64px)',
        position: 'sticky',
        top: 64,
        overflow: 'auto',
      }}
    >
      <div style={{ padding: '16px 12px' }}>
        <Menu
          mode="inline"
          items={items}
          selectedKeys={[selectedKey, location.pathname]}
          onClick={({ key }) => navigate(key)}
          style={{ border: 'none', background: 'transparent' }}
        />
      </div>
    </Sider>
  )
}
