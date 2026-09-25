// The shapes the backend returns (mirrors backend/app/schemas). Keep in sync with docs/api.md.

export type Role = 'CUSTOMER' | 'SUPPORT_AGENT' | 'SUPPORT_MANAGER' | 'ADMIN'
export type TicketStatus = 'OPEN' | 'IN_PROGRESS' | 'WAITING_FOR_CUSTOMER' | 'ESCALATED' | 'RESOLVED' | 'CLOSED'
export type TicketPriority = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
export type TicketCategory = 'BILLING' | 'PAYMENT' | 'TECHNICAL' | 'ACCOUNT' | 'LOGIN' | 'PRODUCT' | 'SECURITY' | 'OTHER'

export const STAFF_ROLES: Role[] = ['SUPPORT_AGENT', 'SUPPORT_MANAGER', 'ADMIN']
export const MANAGER_ROLES: Role[] = ['SUPPORT_MANAGER', 'ADMIN']
export const CATEGORIES: TicketCategory[] = ['BILLING', 'PAYMENT', 'TECHNICAL', 'ACCOUNT', 'LOGIN', 'PRODUCT', 'SECURITY', 'OTHER']
export const PRIORITIES: TicketPriority[] = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
export const STATUSES: TicketStatus[] = ['OPEN', 'IN_PROGRESS', 'WAITING_FOR_CUSTOMER', 'ESCALATED', 'RESOLVED', 'CLOSED']

export interface User {
  id: string
  email: string
  full_name: string
  role: Role
  is_active: boolean
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: User
}

export interface UserRef {
  id: string
  full_name: string
}

export interface Ticket {
  id: string
  number: number
  subject: string
  status: TicketStatus
  priority: TicketPriority
  category: TicketCategory | null
  customer: UserRef
  team: { id: string; name: string } | null
  assignee: UserRef | null
  created_at: string
  resolved_at: string | null
}

export interface Message {
  id: string
  author: UserRef
  body: string
  is_internal: boolean
  created_at: string
}

export interface HistoryEntry {
  from_status: TicketStatus | null
  to_status: TicketStatus
  changed_by: UserRef | null // null = done by the system (e.g. the SLA check)
  reason: string | null
  created_at: string
}

export interface AgentStep {
  tool: string
  arguments: Record<string, unknown>
  ok: boolean
  blocked: boolean
  output: Record<string, unknown>
}

export interface AIInteraction {
  kind: 'classification' | 'reply_suggestion' | 'agent_run' | string
  status: 'OK' | 'INVALID_OUTPUT' | 'UNAVAILABLE'
  model: string
  prompt_version: string
  result: Record<string, unknown> | null
  confidence: number | null
  applied: boolean
  decision: string | null
  latency_ms: number | null
  created_at: string
}

export interface Team {
  id: string
  name: string
  description: string | null
  is_active: boolean
  members: { user: UserRef; is_lead: boolean }[]
}

export interface Source {
  document_id: string
  title: string
  chunk_index: number
  similarity: number
  excerpt: string
}

export interface Answer {
  answerable: boolean
  answer: string
  sources: Source[]
  reason: string
  latency_ms: number | null
}

export interface KnowledgeDocument {
  id: string
  title: string
  filename: string
  status: 'PROCESSING' | 'READY' | 'FAILED'
  chunk_count: number
  error: string | null
  created_at: string
}
