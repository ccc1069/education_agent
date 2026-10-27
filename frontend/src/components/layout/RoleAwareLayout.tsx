import type { ReactNode } from 'react'
import { AppShell } from './AppShell'

interface RoleAwareLayoutProps {
  children: ReactNode
}

/** 角色感知布局:目前所有角色共享 AppShell,侧边栏菜单根据角色渲染 */
export function RoleAwareLayout({ children }: RoleAwareLayoutProps) {
  return <AppShell>{children}</AppShell>
}
