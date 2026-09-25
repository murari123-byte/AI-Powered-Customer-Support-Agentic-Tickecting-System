import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'
import type { TokenResponse } from './types'

/*
 * One shared Axios instance for the whole app.
 *
 * Login flow:
 * - The ACCESS token lives only in memory (this module), never in localStorage, where any
 *   injected script could read it.
 * - The REFRESH token is an httpOnly cookie the browser sends by itself (withCredentials),
 *   and JavaScript can't read it at all.
 * - When a call gets 401 (access token expired), we refresh once and repeat the call.
 */
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000',
  timeout: 15_000,
  withCredentials: true, // send the refresh cookie to /api/v1/auth/*
})

/** Longer timeout for calls that run the LLM while you wait (a CPU can take 20-30 s). */
export const AI_TIMEOUT = 120_000

let accessToken: string | null = null
let onSessionEnded: () => void = () => {}

export function setAccessToken(token: string | null) {
  accessToken = token
}

/** Called when the session can't be refreshed any more (e.g. the refresh token expired). */
export function onSessionEnd(callback: () => void) {
  onSessionEnded = callback
}

apiClient.interceptors.request.use((config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`
  return config
})

// If several calls fail at the same moment, they all wait for ONE refresh (a refresh token works only once).
let refreshing: Promise<TokenResponse> | null = null

export function refreshSession(): Promise<TokenResponse> {
  refreshing ??= apiClient
    .post<TokenResponse>('/api/v1/auth/refresh')
    .then(({ data }) => {
      setAccessToken(data.access_token)
      return data
    })
    .finally(() => {
      refreshing = null
    })
  return refreshing
}

apiClient.interceptors.response.use(undefined, async (error: AxiosError) => {
  const original = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined
  const isAuthCall = original?.url?.startsWith('/api/v1/auth/')
  if (error.response?.status !== 401 || !original || original._retried || isAuthCall) {
    return Promise.reject(error)
  }
  original._retried = true
  try {
    await refreshSession()
  } catch {
    setAccessToken(null)
    onSessionEnded()
    return Promise.reject(error)
  }
  return apiClient(original)
})

/** A readable message from any API error ({"detail": "..."} or FastAPI's validation list). */
export function errorText(error: unknown): string {
  if (error instanceof AxiosError) {
    const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail[0]?.msg) return `${detail[0].loc?.slice(-1)[0] ?? 'input'}: ${detail[0].msg}`
    if (error.code === 'ECONNABORTED') return 'The server took too long to answer.'
    if (!error.response) return 'Cannot reach the server. Is the backend running?'
    return `Request failed (${error.response.status})`
  }
  return error instanceof Error ? error.message : 'Something went wrong'
}
