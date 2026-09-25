import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { describe, expect, it } from 'vitest'
import type { User } from '../api/types'
import { AuthContext, type AuthState } from '../auth/useAuth'
import { RequireAuth, StatusBadge } from '../components/Layout'

function withUser(user: User | null) {
  const auth: AuthState = {
    user,
    loading: false,
    login: async () => {},
    logout: async () => {},
    isStaff: !!user && user.role !== 'CUSTOMER',
    isManager: false,
    isAdmin: user?.role === 'ADMIN',
  }
  return render(
    <AuthContext.Provider value={auth}>
      <MemoryRouter initialEntries={['/admin']}>
        <Routes>
          <Route path="/login" element={<p>login page</p>} />
          <Route path="/tickets" element={<p>tickets page</p>} />
          <Route
            path="/admin"
            element={
              <RequireAuth roles={['ADMIN']}>
                <p>admin page</p>
              </RequireAuth>
            }
          />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  )
}

const user = (role: User['role']): User => ({ id: '1', email: 'a@example.com', full_name: 'A', role, is_active: true, created_at: '' })

describe('RequireAuth', () => {
  it('sends visitors to the login page', () => {
    withUser(null)
    expect(screen.getByText('login page')).toBeInTheDocument()
  })

  it('sends users without the role back to their tickets', () => {
    withUser(user('SUPPORT_AGENT'))
    expect(screen.getByText('tickets page')).toBeInTheDocument()
  })

  it('shows the page to the right role', () => {
    withUser(user('ADMIN'))
    expect(screen.getByText('admin page')).toBeInTheDocument()
  })
})

describe('StatusBadge', () => {
  it('shows a readable status', () => {
    render(<StatusBadge status="WAITING_FOR_CUSTOMER" />)
    expect(screen.getByText('WAITING FOR CUSTOMER')).toHaveClass('badge-waiting_for_customer')
  })
})
