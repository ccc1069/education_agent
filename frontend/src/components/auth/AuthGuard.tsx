import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import type { Role } from '@/types/user'
import { useAuthStore } from '@/lib/store/authStore'

interface AuthGuardProps {
  children: ReactNode
  allow?: Role[]
  /** 登录后默认跳转 */
  fallback?: string
}

/** 路由守卫:未登录跳 /login,角色不匹配跳 fallback */
export function AuthGuard({ children, allow, fallback }: AuthGuardProps) {
  const location = useLocation()
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const user = useAuthStore((s) => s.user)

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (allow && !allow.includes(user.role)) {
    const target = fallback ?? defaultFallback(user.role)
    return <Navigate to={target} replace />
  }

  return <>{children}</>
}

function defaultFallback(role: Role): string {
  switch (role) {
    case 'student':
      return '/learn'
    case 'teacher':
      return '/teacher/classes'
    case 'admin':
      return '/admin/audit'
    default:
      return '/login'
  }
}
