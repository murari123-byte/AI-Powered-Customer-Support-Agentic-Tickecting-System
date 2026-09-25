import { createContext, useContext } from 'react'
import type { User } from '../api/types'

export interface AuthState {
  user: User | null
  loading: boolean // true while we check for an existing session on page load
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  isStaff: boolean
  isManager: boolean
  isAdmin: boolean
}

export const AuthContext = createContext<AuthState | null>(null)

/** The logged-in user and login/logout, from anywhere inside <AuthProvider>. */
export function useAuth(): AuthState {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}
