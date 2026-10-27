/** 用户与角色 */
export type Role = 'student' | 'teacher' | 'admin'

export interface User {
  id: number
  email: string
  role: Role
  learner_id: string | null
  name?: string | null
  tenant_id?: number | null
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: 'bearer'
  expires_in_seconds: number
  user: User
}

export interface RegisterResponse {
  user_id: number
  learner_id: string
  message: string
}
