import { Link, NavLink, Navigate, Outlet, useLocation } from 'react-router'
import type { Role } from '../api/types'
import { useAuth } from '../auth/useAuth'

/** Page frame with a role-aware menu. Only for logged-in users. */
export function Layout() {
  const { user, isStaff, isAdmin, logout } = useAuth()
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/tickets" className="brand">
          AI Support
        </Link>
        <nav>
          <NavLink to="/tickets">{isStaff ? 'Ticket queue' : 'My tickets'}</NavLink>
          {!isStaff && <NavLink to="/tickets/new">New ticket</NavLink>}
          {isStaff && <NavLink to="/knowledge">Knowledge base</NavLink>}
          {isAdmin && <NavLink to="/admin">Admin</NavLink>}
        </nav>
        <div className="who">
          <span>
            {user?.full_name} <small className="muted">({user?.role.replace('SUPPORT_', '').toLowerCase()})</small>
          </span>
          <button type="button" className="link" onClick={() => void logout()}>
            Log out
          </button>
        </div>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}

/** Send visitors to /login, and users without the right role back to their tickets. */
export function RequireAuth({ roles, children }: { roles?: Role[]; children: React.ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <p className="page muted">Loading…</p>
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (roles && !roles.includes(user.role)) return <Navigate to="/tickets" replace />
  return <>{children}</>
}

export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge badge-${status.toLowerCase()}`}>{status.replaceAll('_', ' ')}</span>
}

export function ErrorBox({ message }: { message: string | null }) {
  return message ? (
    <p className="error" role="alert">
      {message}
    </p>
  ) : null
}
