import { Navigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/lib/store/authStore'

/** 已登录用户访问 /login /register 时重定向到对应首页 */
export function RedirectIfAuthed({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const user = useAuthStore((s) => s.user)

  if (isAuthenticated && user) {
    const target =
      (location.state as { from?: { pathname: string } } | null)?.from?.pathname ??
      (user.role === 'student'
        ? '/learn'
        : user.role === 'teacher'
          ? '/teacher/classes'
          : '/admin/audit')
    return <Navigate to={target} replace />
  }
  return <>{children}</>
}
