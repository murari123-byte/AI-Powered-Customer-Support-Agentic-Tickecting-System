import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { errorText } from '../api/client'
import * as api from '../api/endpoints'
import { STAFF_ROLES, type Role, type Team, type User } from '../api/types'
import { useAuth } from '../auth/useAuth'
import { ErrorBox } from '../components/Layout'

const ROLES: Role[] = ['CUSTOMER', 'SUPPORT_AGENT', 'SUPPORT_MANAGER', 'ADMIN']

export function AdminPage() {
  const { user: me } = useAuth()
  const [users, setUsers] = useState<User[]>([])
  const [teams, setTeams] = useState<Team[]>([])
  const [search, setSearch] = useState('')
  const [newTeam, setNewTeam] = useState('')
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [u, t] = await Promise.all([api.listUsers(search), api.listTeams()])
      setUsers(u.items)
      setTeams(t)
    } catch (err) {
      setError(errorText(err))
    }
  }, [search])

  useEffect(() => {
    // The state is set after the request finishes (after an await), not synchronously.
    // oxlint-disable-next-line react/set-state-in-effect
    void load()
  }, [load])

  async function act(action: () => Promise<unknown>) {
    setError(null)
    try {
      await action()
      await load()
    } catch (err) {
      setError(errorText(err))
    }
  }

  function createTeam(event: FormEvent) {
    event.preventDefault()
    void act(() => api.createTeam(newTeam, '')).then(() => setNewTeam(''))
  }

  const staff = users.filter((u) => STAFF_ROLES.includes(u.role) && u.is_active)

  return (
    <section>
      <h1>Admin</h1>
      <ErrorBox message={error} />

      <h2>Users</h2>
      <input placeholder="Search name or email…" value={search} onChange={(e) => setSearch(e.target.value)} />
      <table className="list">
        <thead>
          <tr>
            <th>Name</th>
            <th>Email</th>
            <th>Role</th>
            <th>Active</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} className={u.is_active ? '' : 'inactive'}>
              <td>{u.full_name}</td>
              <td>{u.email}</td>
              <td>
                <select value={u.role} disabled={u.id === me?.id} onChange={(e) => act(() => api.updateUser(u.id, { role: e.target.value as Role }))}>
                  {ROLES.map((r) => (
                    <option key={r}>{r}</option>
                  ))}
                </select>
              </td>
              <td>
                <input type="checkbox" checked={u.is_active} disabled={u.id === me?.id} onChange={(e) => act(() => api.updateUser(u.id, { is_active: e.target.checked }))} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Teams</h2>
      <form className="inline-form" onSubmit={createTeam}>
        <input value={newTeam} onChange={(e) => setNewTeam(e.target.value)} placeholder="New team name" minLength={2} maxLength={100} required />
        <button type="submit">Create team</button>
      </form>
      <div className="teams">
        {teams.map((team) => (
          <div key={team.id} className="card">
            <h3>{team.name}</h3>
            <ul>
              {team.members.map((m) => (
                <li key={m.user.id}>
                  {m.user.full_name} {m.is_lead && <span className="tag">lead</span>}{' '}
                  <button type="button" className="link" onClick={() => act(() => api.removeTeamMember(team.id, m.user.id))}>
                    remove
                  </button>
                </li>
              ))}
              {team.members.length === 0 && <li className="muted">No members</li>}
            </ul>
            <select
              value=""
              onChange={(e) => e.target.value && act(() => api.addTeamMember(team.id, e.target.value, false))}
            >
              <option value="">Add a staff member…</option>
              {staff
                .filter((u) => !team.members.some((m) => m.user.id === u.id))
                .map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name} ({u.role.replace('SUPPORT_', '').toLowerCase()})
                  </option>
                ))}
            </select>
          </div>
        ))}
      </div>
    </section>
  )
}
