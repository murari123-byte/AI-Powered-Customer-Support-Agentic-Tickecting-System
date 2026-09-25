import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { onSessionEnd, refreshSession, setAccessToken } from '../api/client'
import * as api from '../api/endpoints'
import { MANAGER_ROLES, STAFF_ROLES, type User } from '../api/types'
import { AuthContext, type AuthState } from './useAuth'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  // On page load there's no access token in memory (it's never saved to disk), so try the
  // refresh cookie: if it's still valid, the user stays logged in after a reload.
  useEffect(() => {
    let ignore = false
    refreshSession()
      .then((session) => !ignore && setUser(session.user))
      .catch(() => !ignore && setUser(null))
      .finally(() => !ignore && setLoading(false))
    onSessionEnd(() => setUser(null))
    return () => {
      ignore = true
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const session = await api.login(email, password)
    setAccessToken(session.access_token)
    setUser(session.user)
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } finally {
      setAccessToken(null)
      setUser(null)
    }
  }, [])

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      login,
      logout,
      isStaff: !!user && STAFF_ROLES.includes(user.role),
      isManager: !!user && MANAGER_ROLES.includes(user.role),
      isAdmin: user?.role === 'ADMIN',
    }),
    [user, loading, login, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
