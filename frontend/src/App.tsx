import { lazy, Suspense, useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Spin } from 'antd'
import { AuthGuard } from '@/components/auth/AuthGuard'
import { RedirectIfAuthed } from '@/components/auth/RedirectIfAuthed'
import { RoleAwareLayout } from '@/components/layout/RoleAwareLayout'
import { useAuthStore } from '@/lib/store/authStore'
import { authApi } from '@/lib/api/auth'

const LoginPage = lazy(() => import('@/pages/auth/LoginPage'))
const RegisterPage = lazy(() => import('@/pages/auth/RegisterPage'))
const LearnCenterPage = lazy(() => import('@/pages/student/LearnCenterPage'))
const KnowledgeLearnPage = lazy(() => import('@/pages/student/KnowledgeLearnPage'))
const PracticePage = lazy(() => import('@/pages/student/PracticePage'))
const StudentAssignmentsPage = lazy(() => import('@/pages/student/AssignmentsPage'))
const VisionPage = lazy(() => import('@/pages/student/VisionPage'))
const ProgressPage = lazy(() => import('@/pages/student/ProgressPage'))
const KnowledgeGraphPage = lazy(() => import('@/pages/student/KnowledgeGraphPage'))
const NotificationsPage = lazy(() => import('@/pages/student/NotificationsPage'))
const ProfilePage = lazy(() => import('@/pages/student/ProfilePage'))

const ClassesPage = lazy(() => import('@/pages/teacher/ClassesPage'))
const ClassDetailPage = lazy(() => import('@/pages/teacher/ClassDetailPage'))
const AssignmentsPage = lazy(() => import('@/pages/teacher/AssignmentsPage'))
const QuestionsPage = lazy(() => import('@/pages/teacher/QuestionsPage'))
const KnowledgeBasePage = lazy(() => import('@/pages/teacher/KnowledgeBasePage'))

const TenantsPage = lazy(() => import('@/pages/admin/TenantsPage'))
const AuditLogsPage = lazy(() => import('@/pages/admin/AuditLogsPage'))
const TasksPage = lazy(() => import('@/pages/admin/TasksPage'))

function PageLoading() {
  return (
    <div className="flex items-center justify-center" style={{ minHeight: '60vh' }}>
      <Spin size="large" />
    </div>
  )
}

export default function App() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const user = useAuthStore((s) => s.user)
  const setUser = useAuthStore((s) => s.setUser)
  const logout = useAuthStore((s) => s.logout)

  // 启动时校验 token 一次；勿依赖 user，否则 setUser 会反复触发 /auth/me
  useEffect(() => {
    if (!isAuthenticated) return
    let cancelled = false
    authApi
      .me()
      .then((fresh) => {
        if (!cancelled) setUser(fresh)
      })
      .catch(() => {
        if (!cancelled) logout()
      })
    return () => {
      cancelled = true
    }
  }, [isAuthenticated, setUser, logout])

  return (
    <Suspense fallback={<PageLoading />}>
      <Routes>
        {/* 公开路由 */}
        <Route
          path="/login"
          element={
            <RedirectIfAuthed>
              <LoginPage />
            </RedirectIfAuthed>
          }
        />
        <Route
          path="/register"
          element={
            <RedirectIfAuthed>
              <RegisterPage />
            </RedirectIfAuthed>
          }
        />

        {/* 学生路由 */}
        <Route
          path="/learn"
          element={
            <AuthGuard allow={['student', 'teacher', 'admin']}>
              <RoleAwareLayout>
                <LearnCenterPage />
              </RoleAwareLayout>
            </AuthGuard>
          }
        />
        <Route
          path="/learn/:knowledgeId"
          element={
            <AuthGuard allow={['student', 'teacher', 'admin']}>
              <RoleAwareLayout>
                <KnowledgeLearnPage />
              </RoleAwareLayout>
            </AuthGuard>
          }
        />
        <Route
          path="/practice"
          element={
            <AuthGuard allow={['student', 'teacher', 'admin']}>
              <RoleAwareLayout>
                <PracticePage />
              </RoleAwareLayout>
            </AuthGuard>
          }
        />
        <Route
          path="/assignments"
          element={
            <AuthGuard allow={['student']} fallback="/learn">
              <RoleAwareLayout>
                <StudentAssignmentsPage />
              </RoleAwareLayout>
            </AuthGuard>
          }
        />
        <Route
          path="/vision"
          element={
            <AuthGuard allow={['student', 'teacher', 'admin']}>
              <RoleAwareLayout>
                <VisionPage />
              </RoleAwareLayout>
            </AuthGuard>
          }
        />
        <Route
          path="/progress"
          element={
            <AuthGuard allow={['student', 'teacher', 'admin']}>
              <RoleAwareLayout>
                <ProgressPage />
              </RoleAwareLayout>
            </AuthGuard>
          }
        />
        <Route
          path="/knowledge-graph"
          element={
            <AuthGuard allow={['student', 'teacher', 'admin']}>
              <RoleAwareLayout>
                <KnowledgeGraphPage />
              </RoleAwareLayout>
            </AuthGuard>
          }
        />
        <Route
          path="/notifications"
          element={
            <AuthGuard>
              <RoleAwareLayout>
                <NotificationsPage />
              </RoleAwareLayout>
            </AuthGuard>
          }
        />
        <Route
          path="/profile"
          element={
            <AuthGuard>
              <RoleAwareLayout>
                <ProfilePage />
              </RoleAwareLayout>
            </AuthGuard>
          }
        />

        {/* 教师路由 */}
        <Route
          path="/teacher/classes"
          element={
            <AuthGuard allow={['teacher', 'admin']} fallback="/learn">
              <RoleAwareLayout>
                <ClassesPage />
              </RoleAwareLayout>
            </AuthGuard>
          }
        />
        <Route
          path="/teacher/classes/:id"
          element={
            <AuthGuard allow={['teacher', 'admin']} fallback="/learn">
              <RoleAwareLayout>
                <ClassDetailPage />
              </RoleAwareLayout>
            </AuthGuard>
          }
        />
        <Route
          path="/teacher/assignments"
          element={
            <AuthGuard allow={['teacher', 'admin']} fallback="/learn">
              <RoleAwareLayout>
                <AssignmentsPage />
              </RoleAwareLayout>
            </AuthGuard>
          }
        />
        <Route
          path="/teacher/questions"
          element={
            <AuthGuard allow={['teacher', 'admin']} fallback="/learn">
              <RoleAwareLayout>
                <QuestionsPage />
              </RoleAwareLayout>
            </AuthGuard>
          }
        />
        <Route
          path="/teacher/knowledge-base"
          element={
            <AuthGuard allow={['teacher', 'admin']} fallback="/learn">
              <RoleAwareLayout>
                <KnowledgeBasePage />
              </RoleAwareLayout>
            </AuthGuard>
          }
        />

        {/* 管理员路由 */}
        <Route
          path="/admin/tenants"
          element={
            <AuthGuard allow={['admin']} fallback="/learn">
              <RoleAwareLayout>
                <TenantsPage />
              </RoleAwareLayout>
            </AuthGuard>
          }
        />
        <Route
          path="/admin/audit"
          element={
            <AuthGuard allow={['admin']} fallback="/learn">
              <RoleAwareLayout>
                <AuditLogsPage />
              </RoleAwareLayout>
            </AuthGuard>
          }
        />
        <Route
          path="/admin/tasks"
          element={
            <AuthGuard allow={['admin']} fallback="/learn">
              <RoleAwareLayout>
                <TasksPage />
              </RoleAwareLayout>
            </AuthGuard>
          }
        />

        {/* 默认重定向 */}
        <Route
          path="/"
          element={
            <Navigate
              to={
                !isAuthenticated
                  ? '/login'
                  : user?.role === 'student'
                    ? '/learn'
                    : user?.role === 'teacher'
                      ? '/teacher/classes'
                      : '/admin/audit'
              }
              replace
            />
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}
