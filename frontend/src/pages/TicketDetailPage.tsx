import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router'
import { errorText } from '../api/client'
import * as api from '../api/endpoints'
import type { AgentStep, AIInteraction, Answer, HistoryEntry, Message, Team, Ticket, TicketStatus } from '../api/types'
import { PRIORITIES } from '../api/types'
import { useAuth } from '../auth/useAuth'
import { ErrorBox, StatusBadge } from '../components/Layout'

/*
 * Buttons offered for each status. This only decides which buttons to SHOW: the backend
 * checks every move again (see ALLOWED_MOVES in backend/app/services/ticket_workflow.py).
 */
const STAFF_MOVES: Partial<Record<TicketStatus, TicketStatus[]>> = {
  OPEN: ['IN_PROGRESS', 'WAITING_FOR_CUSTOMER', 'RESOLVED'],
  IN_PROGRESS: ['WAITING_FOR_CUSTOMER', 'RESOLVED'],
  WAITING_FOR_CUSTOMER: ['IN_PROGRESS', 'RESOLVED'],
  RESOLVED: ['OPEN', 'CLOSED'],
}
const MANAGER_MOVES: Partial<Record<TicketStatus, TicketStatus[]>> = { ESCALATED: ['IN_PROGRESS', 'RESOLVED'] }
const CUSTOMER_MOVES: Partial<Record<TicketStatus, TicketStatus[]>> = {
  OPEN: ['CLOSED'],
  IN_PROGRESS: ['CLOSED'],
  WAITING_FOR_CUSTOMER: ['CLOSED'],
  RESOLVED: ['OPEN', 'CLOSED'],
}

export function TicketDetailPage() {
  const { id = '' } = useParams()
  const { isStaff, isManager } = useAuth()
  const [ticket, setTicket] = useState<Ticket | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    try {
      const [t, m] = await Promise.all([api.getTicket(id), api.listMessages(id)])
      setTicket(t)
      setMessages(m)
      setError(null)
    } catch (err) {
      setError(errorText(err))
    }
  }, [id])

  useEffect(() => {
    // The state is set after the request finishes (after an await), not synchronously.
    // oxlint-disable-next-line react/set-state-in-effect
    void reload()
  }, [reload])

  async function act(action: () => Promise<unknown>) {
    try {
      await action()
      await reload()
    } catch (err) {
      setError(errorText(err))
    }
  }

  if (!ticket) return error ? <ErrorBox message={error} /> : <p className="muted">Loading…</p>

  const moves = isStaff
    ? [...(STAFF_MOVES[ticket.status] ?? []), ...(isManager ? (MANAGER_MOVES[ticket.status] ?? []) : [])]
    : (CUSTOMER_MOVES[ticket.status] ?? [])

  return (
    <section>
      <p>
        <Link to="/tickets">← Back</Link>
      </p>
      <div className="row">
        <h1>
          #{ticket.number} {ticket.subject}
        </h1>
        <StatusBadge status={ticket.status} />
      </div>
      <p className="muted">
        {ticket.priority} priority · {ticket.category ?? 'no category yet'} · team {ticket.team?.name ?? 'not assigned yet'}
        {ticket.assignee && ` · ${ticket.assignee.full_name}`} · raised by {ticket.customer.full_name}
      </p>
      <ErrorBox message={error} />

      <div className={isStaff ? 'two-columns' : ''}>
        <div>
          <Conversation messages={messages} customerId={ticket.customer.id} />
          {ticket.status !== 'CLOSED' && <ReplyBox ticketId={ticket.id} isStaff={isStaff} onSent={reload} />}
          {moves.length > 0 && (
            <div className="actions">
              {moves.map((status) => (
                <button key={status} type="button" className="secondary" onClick={() => act(() => api.changeStatus(ticket.id, status))}>
                  {status === 'OPEN' && ticket.status === 'RESOLVED' ? 'Reopen' : `Mark ${status.replaceAll('_', ' ').toLowerCase()}`}
                </button>
              ))}
            </div>
          )}
        </div>
        {isStaff && (
          <aside>
            <StaffPanel ticket={ticket} act={act} />
            <AIPanel ticket={ticket} onChanged={reload} />
            <HistoryPanel ticketId={ticket.id} version={ticket.status} />
          </aside>
        )}
      </div>
    </section>
  )
}

function Conversation({ messages, customerId }: { messages: Message[]; customerId: string }) {
  return (
    <div className="conversation">
      {messages.map((m) => (
        <div key={m.id} className={`message ${m.author.id === customerId ? 'from-customer' : 'from-staff'} ${m.is_internal ? 'internal' : ''}`}>
          <div className="meta">
            {m.author.full_name}
            {m.is_internal && <span className="tag">internal note</span>} · {new Date(m.created_at).toLocaleString()}
          </div>
          <div className="body">{m.body}</div>
        </div>
      ))}
    </div>
  )
}

function ReplyBox({ ticketId, isStaff, onSent }: { ticketId: string; isStaff: boolean; onSent: () => void }) {
  const [body, setBody] = useState('')
  const [internal, setInternal] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // While sending, the box is locked: otherwise text typed during the request would be wiped
  // when the box is cleared after it succeeds.
  const [sending, setSending] = useState(false)
  // Lets the AI panel put a suggested reply into this box (the staff member still decides to send it).
  useEffect(() => {
    const fill = (event: Event) => setBody((event as CustomEvent<string>).detail)
    window.addEventListener('fill-reply', fill)
    return () => window.removeEventListener('fill-reply', fill)
  }, [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSending(true)
    setError(null)
    try {
      await api.addMessage(ticketId, body, internal)
      setBody('')
      setInternal(false)
      onSent()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setSending(false)
    }
  }

  return (
    <form className="reply" onSubmit={submit}>
      <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={4} placeholder="Write a reply…" required maxLength={10000} disabled={sending} />
      <div className="row">
        {isStaff ? (
          <label className="inline">
            <input type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} />
            Internal note (customer won't see it)
          </label>
        ) : (
          <span />
        )}
        <button type="submit" disabled={sending}>
          {sending ? 'Sending…' : internal ? 'Add note' : 'Send reply'}
        </button>
      </div>
      <ErrorBox message={error} />
    </form>
  )
}

function StaffPanel({ ticket, act }: { ticket: Ticket; act: (action: () => Promise<unknown>) => Promise<void> }) {
  const { user, isManager } = useAuth()
  const [teams, setTeams] = useState<Team[]>([])
  const [reason, setReason] = useState('')

  useEffect(() => {
    api.listTeams().then(setTeams).catch(() => setTeams([]))
  }, [])

  const team = teams.find((t) => t.id === ticket.team?.id)
  return (
    <div className="card">
      <h3>Work this ticket</h3>
      <label>
        Priority
        <select value={ticket.priority} onChange={(e) => act(() => api.updateTicket(ticket.id, { priority: e.target.value as Ticket['priority'] }))}>
          {PRIORITIES.map((p) => (
            <option key={p}>{p}</option>
          ))}
        </select>
      </label>
      {isManager ? (
        <>
          <label>
            Team
            <select value={ticket.team?.id ?? ''} onChange={(e) => e.target.value && act(() => api.assignTicket(ticket.id, e.target.value, null))}>
              <option value="">Not assigned</option>
              {teams.filter((t) => t.is_active).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
          {team && (
            <label>
              Person
              <select
                value={ticket.assignee?.id ?? ''}
                onChange={(e) => act(() => api.assignTicket(ticket.id, team.id, e.target.value || null))}
              >
                <option value="">Team queue (nobody yet)</option>
                {team.members.map((m) => (
                  <option key={m.user.id} value={m.user.id}>
                    {m.user.full_name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </>
      ) : (
        ticket.team &&
        ticket.assignee?.id !== user?.id && (
          <button type="button" className="secondary" onClick={() => act(() => api.assignTicket(ticket.id, null, user!.id))}>
            Take this ticket
          </button>
        )
      )}
      {['OPEN', 'IN_PROGRESS', 'WAITING_FOR_CUSTOMER'].includes(ticket.status) && (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void act(() => api.escalateTicket(ticket.id, reason)).then(() => setReason(''))
          }}
        >
          <label>
            Escalate to a manager
            <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why?" minLength={3} required />
          </label>
          <button type="submit" className="danger">
            Escalate
          </button>
        </form>
      )}
    </div>
  )
}

function AIPanel({ ticket, onChanged }: { ticket: Ticket; onChanged: () => void }) {
  const [history, setHistory] = useState<AIInteraction[]>([])
  const [suggestion, setSuggestion] = useState<Answer | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => api.getAIHistory(ticket.id).then(setHistory).catch(() => setHistory([])), [ticket.id])
  useEffect(() => {
    void load()
  }, [load])

  // While an agent run is queued, check every 5 seconds whether it has finished.
  const waitingForAgent = busy === 'agent'
  useEffect(() => {
    if (!waitingForAgent) return
    const started = history.filter((h) => h.kind === 'agent_run').length
    const timer = window.setInterval(async () => {
      const latest = await api.getAIHistory(ticket.id)
      if (latest.filter((h) => h.kind === 'agent_run').length > started) {
        setHistory(latest)
        setBusy(null)
        onChanged()
      }
    }, 5000)
    return () => window.clearInterval(timer)
  }, [waitingForAgent, ticket.id, history, onChanged])

  async function suggest() {
    setBusy('suggest')
    setError(null)
    try {
      setSuggestion(await api.suggestReply(ticket.id))
      await load()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(null)
    }
  }

  async function runAgent() {
    setError(null)
    try {
      await api.startAgent(ticket.id)
      setBusy('agent')
    } catch (err) {
      setError(errorText(err))
    }
  }

  const triage = history.filter((h) => h.kind === 'classification').at(-1)
  const agentRun = history.filter((h) => h.kind === 'agent_run').at(-1)
  const finished = ticket.status === 'RESOLVED' || ticket.status === 'CLOSED'

  return (
    <div className="card ai">
      <h3>AI assistant</h3>
      {triage ? (
        <div className="ai-block">
          <strong>Auto-triage:</strong>{' '}
          {triage.result ? `${triage.result.category} / ${triage.result.priority} (confidence ${triage.confidence})` : triage.status}
          <div className="muted small">{triage.decision}</div>
          {typeof triage.result?.reasoning === 'string' && <div className="small">“{triage.result.reasoning}”</div>}
        </div>
      ) : (
        <p className="muted small">No auto-triage yet (it runs in the background after the ticket is created).</p>
      )}

      <div className="actions">
        <button type="button" onClick={suggest} disabled={!!busy}>
          {busy === 'suggest' ? 'Thinking… (up to 30 s)' : 'Suggest a reply'}
        </button>
        <button type="button" className="secondary" onClick={runAgent} disabled={!!busy || finished}>
          {busy === 'agent' ? 'Agent working… (about a minute)' : 'Let the AI agent work it'}
        </button>
      </div>
      <ErrorBox message={error} />

      {suggestion && (
        <div className="ai-block">
          <strong>Suggested reply</strong> <span className="muted small">(from the knowledge base; not sent)</span>
          <p>{suggestion.answer}</p>
          {suggestion.sources.map((s) => (
            <details key={`${s.document_id}-${s.chunk_index}`} className="small">
              <summary>
                Source: {s.title} (similarity {s.similarity.toFixed(2)})
              </summary>
              <pre>{s.excerpt}</pre>
            </details>
          ))}
          {suggestion.answerable && (
            <button type="button" className="secondary" onClick={() => window.dispatchEvent(new CustomEvent('fill-reply', { detail: suggestion.answer }))}>
              Use as reply
            </button>
          )}
        </div>
      )}

      {agentRun && <AgentRun run={agentRun} />}
    </div>
  )
}

function AgentRun({ run }: { run: AIInteraction }) {
  const result = run.result as { steps?: AgentStep[]; final?: string; read_only?: boolean } | null
  const draft = result?.final?.split(/DRAFT REPLY:/i)[1]?.trim()
  return (
    <div className="ai-block">
      <strong>Last agent run</strong> <span className="muted small">{run.latency_ms ? `${Math.round(run.latency_ms / 1000)} s` : ''}</span>
      {result?.read_only && <p className="error small">Read-only: the ticket looked like it tried to instruct the AI.</p>}
      <ol className="steps small">
        {(result?.steps ?? []).map((step, i) => (
          <li key={i} className={step.blocked ? 'blocked' : ''}>
            <code>
              {step.tool}({Object.entries(step.arguments).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ')})
            </code>{' '}
            {step.blocked ? `⛔ ${String(step.output.error)}` : step.ok ? '✓' : `✗ ${String(step.output.error ?? '')}`}
          </li>
        ))}
      </ol>
      <div className="muted small">{run.decision}</div>
      {result?.final && <pre className="final">{result.final}</pre>}
      {draft && (
        <button type="button" className="secondary" onClick={() => window.dispatchEvent(new CustomEvent('fill-reply', { detail: draft }))}>
          Use draft as reply
        </button>
      )}
    </div>
  )
}

function HistoryPanel({ ticketId, version }: { ticketId: string; version: string }) {
  const [history, setHistory] = useState<HistoryEntry[]>([])
  useEffect(() => {
    api.getHistory(ticketId).then(setHistory).catch(() => setHistory([]))
  }, [ticketId, version])
  return (
    <div className="card">
      <h3>History</h3>
      <ul className="history small">
        {history.map((h, i) => (
          <li key={i}>
            {new Date(h.created_at).toLocaleString()}: {h.from_status ?? 'new'} → <strong>{h.to_status}</strong> by{' '}
            {h.changed_by?.full_name ?? 'the system'}
            {h.reason && <span className="muted"> ({h.reason})</span>}
          </li>
        ))}
      </ul>
    </div>
  )
}
