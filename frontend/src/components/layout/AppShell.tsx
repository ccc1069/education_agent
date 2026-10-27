import { Layout } from 'antd'
import type { ReactNode } from 'react'
import { TopNav } from './TopNav'
import { SideNav } from './SideNav'

const { Content } = Layout

interface AppShellProps {
  children: ReactNode
}

export function AppShell({ children }: AppShellProps) {
  return (
    <Layout style={{ minHeight: '100vh', background: 'var(--color-paper)' }}>
      <TopNav />
      <Layout>
        <SideNav />
        <Content
          style={{
            padding: 24,
            minHeight: 'calc(100vh - 64px)',
          }}
        >
          {children}
        </Content>
      </Layout>
    </Layout>
  )
}
