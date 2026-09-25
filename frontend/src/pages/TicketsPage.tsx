import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { errorText } from '../api/client'
import * as api from '../api/endpoints'
import { CATEGORIES, PRIORITIES, STATUSES, type Ticket, type TicketCategory } from '../api/types'
import { useAuth } from '../auth/useAuth'
import { ErrorBox, StatusBadge } from '../components/Layout'

export function TicketsPage() {
  const { isStaff } = useAuth()
  const [filters, setFilters] = useState<api.TicketFilters>({ status: '', priority: '', assigned_to_me: false, search: '' })
  const [tickets, setTickets] = useState<Ticket[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let ignore = false
    api
      .listTickets(filters)
      .then((page) => !ignore && setTickets(page.items))
      .catch((err) => !ignore && setError(errorText(err)))
    return () => {
      ignore = true
    }
  }, [filters])

  return (
    <section>
      <div className="row">
        <h1>{isStaff ? 'Ticket queue' : 'My tickets'}</h1>
        {!isStaff && (
          <Link className="button" to="/tickets/new">
            New ticket
          </Link>
        )}
      </div>

      <div className="filters">
        <input placeholder="Search subject…" value={filters.search} onChange={(e) => setFilters({ ...filters, search: e.target.value })} />
        <select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value as api.TicketFilters['status'] })}>
          <option value="">Any status</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s.replaceAll('_', ' ')}
            </option>
          ))}
        </select>
        <select value={filters.priority} onChange={(e) => setFilters({ ...filters, priority: e.target.value as api.TicketFilters['priority'] })}>
          <option value="">Any priority</option>
          {PRIORITIES.map((p) => (
            <option key={p}>{p}</option>
          ))}
        </select>
        {isStaff && (
          <label className="inline">
            <input type="checkbox" checked={filters.assigned_to_me} onChange={(e) => setFilters({ ...filters, assigned_to_me: e.target.checked })} />
            Assigned to me
          </label>
        )}
      </div>

      <ErrorBox message={error} />
      {tickets === null ? (
        <p className="muted">Loading…</p>
      ) : tickets.length === 0 ? (
        <p className="muted">No tickets.</p>
      ) : (
        <table className="list">
          <thead>
            <tr>
              <th>#</th>
              <th>Subject</th>
              <th>Status</th>
              <th>Priority</th>
              <th>Category</th>
              {isStaff && <th>Team</th>}
              {isStaff && <th>Customer</th>}
            </tr>
          </thead>
          <tbody>
            {tickets.map((t) => (
              <tr key={t.id}>
                <td>{t.number}</td>
                <td>
                  <Link to={`/tickets/${t.id}`}>{t.subject}</Link>
                </td>
                <td>
                  <StatusBadge status={t.status} />
                </td>
                <td>{t.priority}</td>
                <td>{t.category ?? <span className="muted">not set</span>}</td>
                {isStaff && <td>{t.team?.name ?? <span className="muted">unrouted</span>}</td>}
                {isStaff && <td>{t.customer.full_name}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

export function NewTicketPage() {
  const navigate = useNavigate()
  const [subject, setSubject] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState<TicketCategory | ''>('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const ticket = await api.createTicket(subject, description, category || null)
      navigate(`/tickets/${ticket.id}`)
    } catch (err) {
      setError(errorText(err))
      setBusy(false)
    }
  }

  return (
    <form className="card narrow" onSubmit={submit}>
      <h1>New ticket</h1>
      <label>
        Subject
        <input value={subject} onChange={(e) => setSubject(e.target.value)} required minLength={3} maxLength={200} />
      </label>
      <label>
        What's the problem?
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} required rows={6} maxLength={10000} />
      </label>
      <label>
        Category <small className="muted">(optional, our AI will also classify it)</small>
        <select value={category} onChange={(e) => setCategory(e.target.value as TicketCategory | '')}>
          <option value="">I'm not sure</option>
          {CATEGORIES.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </label>
      <ErrorBox message={error} />
      <button type="submit" disabled={busy}>
        {busy ? 'Sending…' : 'Send ticket'}
      </button>
    </form>
  )
}
