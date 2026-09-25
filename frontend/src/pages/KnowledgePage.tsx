import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { errorText } from '../api/client'
import * as api from '../api/endpoints'
import type { Answer, KnowledgeDocument } from '../api/types'
import { useAuth } from '../auth/useAuth'
import { ErrorBox, StatusBadge } from '../components/Layout'

export function KnowledgePage() {
  const { isAdmin } = useAuth()
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<Answer | null>(null)
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadDocuments = useCallback(() => api.listDocuments().then(setDocuments).catch((err) => setError(errorText(err))), [])
  useEffect(() => {
    void loadDocuments()
  }, [loadDocuments])

  async function ask(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setAnswer(null)
    try {
      setAnswer(await api.askKnowledgeBase(question))
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  async function upload(file: File | undefined) {
    if (!file) return
    setError(null)
    try {
      await api.uploadDocument(file)
      await loadDocuments()
    } catch (err) {
      setError(errorText(err))
    }
  }

  async function remove(document: KnowledgeDocument) {
    if (!window.confirm(`Delete "${document.title}"?`)) return
    try {
      await api.deleteDocument(document.id)
      await loadDocuments()
    } catch (err) {
      setError(errorText(err))
    }
  }

  return (
    <section>
      <h1>Knowledge base</h1>
      <form className="card" onSubmit={ask}>
        <label>
          Ask a question <small className="muted">(answered only from the documents below, with sources)</small>
          <input value={question} onChange={(e) => setQuestion(e.target.value)} minLength={3} maxLength={1000} required placeholder="How long is the password reset link valid?" />
        </label>
        <button type="submit" disabled={busy}>
          {busy ? 'Thinking… (up to 30 s)' : 'Ask'}
        </button>
      </form>
      <ErrorBox message={error} />

      {answer && (
        <div className={`card ${answer.answerable ? '' : 'not-found'}`}>
          <p>{answer.answer}</p>
          <p className="muted small">
            {answer.reason}
            {answer.latency_ms ? ` · ${(answer.latency_ms / 1000).toFixed(1)} s` : ''}
          </p>
          {answer.sources.map((s) => (
            <details key={`${s.document_id}-${s.chunk_index}`}>
              <summary>
                Source: {s.title} (similarity {s.similarity.toFixed(2)})
              </summary>
              <pre>{s.excerpt}</pre>
            </details>
          ))}
        </div>
      )}

      <div className="row">
        <h2>Documents</h2>
        {isAdmin && (
          <label className="button">
            Upload .md / .txt / .pdf
            <input type="file" accept=".md,.txt,.pdf" hidden onChange={(e) => void upload(e.target.files?.[0])} />
          </label>
        )}
      </div>
      <table className="list">
        <thead>
          <tr>
            <th>Title</th>
            <th>File</th>
            <th>Status</th>
            <th>Chunks</th>
            {isAdmin && <th />}
          </tr>
        </thead>
        <tbody>
          {documents.map((d) => (
            <tr key={d.id}>
              <td>{d.title}</td>
              <td className="muted">{d.filename}</td>
              <td>
                <StatusBadge status={d.status} /> {d.error && <span className="error small">{d.error}</span>}
              </td>
              <td>{d.chunk_count}</td>
              {isAdmin && (
                <td>
                  <button type="button" className="link" onClick={() => void remove(d)}>
                    Delete
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {documents.some((d) => d.status === 'PROCESSING') && (
        <p className="muted small">
          Documents marked PROCESSING are being embedded by the background worker. <button type="button" className="link" onClick={() => void loadDocuments()}>Refresh</button>
        </p>
      )}
    </section>
  )
}
