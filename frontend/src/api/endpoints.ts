// Every backend call the app makes, in one place. Pages never build URLs themselves.
import { AI_TIMEOUT, apiClient } from './client'
import type {
  AIInteraction,
  Answer,
  HistoryEntry,
  KnowledgeDocument,
  Message,
  Role,
  Team,
  Ticket,
  TicketCategory,
  TicketPriority,
  TicketStatus,
  TokenResponse,
  User,
} from './types'

// ---------- Auth ----------

export const login = (email: string, password: string) =>
  apiClient.post<TokenResponse>('/api/v1/auth/login', { email, password }).then((r) => r.data)

export const register = (email: string, password: string, full_name: string) =>
  apiClient.post<User>('/api/v1/auth/register', { email, password, full_name }).then((r) => r.data)

export const logout = () => apiClient.post('/api/v1/auth/logout')

// ---------- Tickets ----------

export interface TicketFilters {
  status?: TicketStatus | ''
  priority?: TicketPriority | ''
  assigned_to_me?: boolean
  search?: string
}

export const listTickets = (filters: TicketFilters = {}) => {
  const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== '' && value !== false))
  return apiClient.get<{ items: Ticket[]; total: number }>('/api/v1/tickets', { params: { limit: 100, ...params } }).then((r) => r.data)
}

export const createTicket = (subject: string, description: string, category: TicketCategory | null) =>
  apiClient.post<Ticket>('/api/v1/tickets', { subject, description, category }).then((r) => r.data)

export const getTicket = (id: string) => apiClient.get<Ticket>(`/api/v1/tickets/${id}`).then((r) => r.data)

export const updateTicket = (id: string, changes: { priority?: TicketPriority; category?: TicketCategory }) =>
  apiClient.patch<Ticket>(`/api/v1/tickets/${id}`, changes).then((r) => r.data)

export const changeStatus = (id: string, status: TicketStatus, reason?: string) =>
  apiClient.post<Ticket>(`/api/v1/tickets/${id}/status`, { status, reason: reason || null }).then((r) => r.data)

export const listMessages = (id: string) => apiClient.get<Message[]>(`/api/v1/tickets/${id}/messages`).then((r) => r.data)

export const addMessage = (id: string, body: string, is_internal: boolean) =>
  apiClient.post<Message>(`/api/v1/tickets/${id}/messages`, { body, is_internal }).then((r) => r.data)

export const assignTicket = (id: string, team_id: string | null, assignee_id: string | null) =>
  apiClient.post<Ticket>(`/api/v1/tickets/${id}/assign`, { team_id, assignee_id }).then((r) => r.data)

export const escalateTicket = (id: string, reason: string) =>
  apiClient.post<Ticket>(`/api/v1/tickets/${id}/escalate`, { reason }).then((r) => r.data)

export const getHistory = (id: string) => apiClient.get<HistoryEntry[]>(`/api/v1/tickets/${id}/history`).then((r) => r.data)

export const getAIHistory = (id: string) => apiClient.get<AIInteraction[]>(`/api/v1/tickets/${id}/ai`).then((r) => r.data)

export const suggestReply = (id: string) =>
  apiClient.post<Answer>(`/api/v1/tickets/${id}/suggest-reply`, null, { timeout: AI_TIMEOUT }).then((r) => r.data)

export const startAgent = (id: string) => apiClient.post(`/api/v1/tickets/${id}/agent`).then((r) => r.data)

// ---------- Teams and users ----------

export const listTeams = () => apiClient.get<Team[]>('/api/v1/teams').then((r) => r.data)

export const createTeam = (name: string, description: string) =>
  apiClient.post<Team>('/api/v1/teams', { name, description: description || null }).then((r) => r.data)

export const addTeamMember = (teamId: string, user_id: string, is_lead: boolean) =>
  apiClient.post<Team>(`/api/v1/teams/${teamId}/members`, { user_id, is_lead }).then((r) => r.data)

export const removeTeamMember = (teamId: string, userId: string) => apiClient.delete(`/api/v1/teams/${teamId}/members/${userId}`)

export const listUsers = (search?: string) =>
  apiClient.get<{ items: User[]; total: number }>('/api/v1/admin/users', { params: { limit: 200, search: search || undefined } }).then((r) => r.data)

export const updateUser = (id: string, changes: { role?: Role; is_active?: boolean }) =>
  apiClient.patch<User>(`/api/v1/admin/users/${id}`, changes).then((r) => r.data)

// ---------- Knowledge base ----------

export const listDocuments = () => apiClient.get<KnowledgeDocument[]>('/api/v1/knowledge').then((r) => r.data)

export const uploadDocument = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return apiClient.post<KnowledgeDocument>('/api/v1/knowledge', form).then((r) => r.data)
}

export const deleteDocument = (id: string) => apiClient.delete(`/api/v1/knowledge/${id}`)

export const askKnowledgeBase = (question: string) =>
  apiClient.post<Answer>('/api/v1/knowledge/ask', { question }, { timeout: AI_TIMEOUT }).then((r) => r.data)
