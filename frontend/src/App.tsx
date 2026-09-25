import { Navigate, Route, Routes } from 'react-router'
import { STAFF_ROLES } from './api/types'
import { AuthProvider } from './auth/AuthContext'
import { Layout, RequireAuth } from './components/Layout'
import { AdminPage } from './pages/AdminPage'
import { KnowledgePage } from './pages/KnowledgePage'
import { LoginPage, RegisterPage } from './pages/LoginPage'
import NotFoundPage from './pages/NotFoundPage'
import { TicketDetailPage } from './pages/TicketDetailPage'
import { NewTicketPage, TicketsPage } from './pages/TicketsPage'

// The menu hides pages a role can't use, and these routes check again. The BACKEND is still the real
// guard: it checks the role on every API call, so hiding a page is only for convenience.
export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route
          element={
            <RequireAuth>
              <Layout />
            </RequireAuth>
          }
        >
          <Route path="/" element={<Navigate to="/tickets" replace />} />
          <Route path="/tickets" element={<TicketsPage />} />
          <Route
            path="/tickets/new"
            element={
              <RequireAuth roles={['CUSTOMER']}>
                <NewTicketPage />
              </RequireAuth>
            }
          />
          <Route path="/tickets/:id" element={<TicketDetailPage />} />
          <Route
            path="/knowledge"
            element={
              <RequireAuth roles={STAFF_ROLES}>
                <KnowledgePage />
              </RequireAuth>
            }
          />
          <Route
            path="/admin"
            element={
              <RequireAuth roles={['ADMIN']}>
                <AdminPage />
              </RequireAuth>
            }
          />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AuthProvider>
  )
}
