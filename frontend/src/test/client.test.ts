import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from 'axios'
import { afterEach, describe, expect, it } from 'vitest'
import { apiClient, errorText, onSessionEnd, setAccessToken } from '../api/client'

// A fake "server" for Axios: each test decides how every request is answered.
function useFakeServer(answer: (config: InternalAxiosRequestConfig) => { status: number; data: unknown }) {
  const calls: InternalAxiosRequestConfig[] = []
  const adapter: AxiosAdapter = async (config) => {
    calls.push(config)
    const { status, data } = answer(config)
    const response = { status, data, statusText: '', headers: {}, config }
    if (status >= 400) throw new AxiosError('failed', String(status), config, null, response)
    return response
  }
  apiClient.defaults.adapter = adapter
  return calls
}

afterEach(() => setAccessToken(null))

describe('api client', () => {
  it('sends the access token', async () => {
    const calls = useFakeServer(() => ({ status: 200, data: {} }))
    setAccessToken('abc')

    await apiClient.get('/api/v1/tickets')

    expect(calls[0].headers.Authorization).toBe('Bearer abc')
  })

  it('refreshes once on 401 and repeats the call with the new token', async () => {
    let refreshed = false
    const calls = useFakeServer((config) => {
      if (config.url === '/api/v1/auth/refresh') {
        refreshed = true
        return { status: 200, data: { access_token: 'new-token', user: {} } }
      }
      return refreshed ? { status: 200, data: { ok: true } } : { status: 401, data: {} }
    })
    setAccessToken('expired')

    const response = await apiClient.get('/api/v1/tickets')

    expect(response.data).toEqual({ ok: true })
    expect(calls.map((c) => c.url)).toEqual(['/api/v1/tickets', '/api/v1/auth/refresh', '/api/v1/tickets'])
    expect(calls[2].headers.Authorization).toBe('Bearer new-token')
  })

  it('two expired calls at once share ONE refresh (a refresh token works only once)', async () => {
    let refreshed = false
    const calls = useFakeServer((config) => {
      if (config.url === '/api/v1/auth/refresh') {
        refreshed = true
        return { status: 200, data: { access_token: 'new', user: {} } }
      }
      return refreshed ? { status: 200, data: {} } : { status: 401, data: {} }
    })

    await Promise.all([apiClient.get('/api/v1/tickets'), apiClient.get('/api/v1/teams')])

    expect(calls.filter((c) => c.url === '/api/v1/auth/refresh')).toHaveLength(1)
  })

  it('ends the session when the refresh fails', async () => {
    useFakeServer(() => ({ status: 401, data: { detail: 'Please log in again' } }))
    let ended = false
    onSessionEnd(() => (ended = true))

    await expect(apiClient.get('/api/v1/tickets')).rejects.toBeInstanceOf(AxiosError)
    expect(ended).toBe(true)
  })
})

describe('errorText', () => {
  const error = (status: number, data: unknown) =>
    new AxiosError('x', String(status), undefined, null, {
      status,
      data,
      statusText: '',
      headers: {},
      config: { headers: new AxiosHeaders() },
    })

  it('shows the API detail message', () => {
    expect(errorText(error(409, { detail: 'Email is already registered' }))).toBe('Email is already registered')
  })

  it('shows the first validation problem', () => {
    expect(errorText(error(422, { detail: [{ loc: ['body', 'password'], msg: 'too short' }] }))).toBe('password: too short')
  })

  it('explains a server that cannot be reached', () => {
    expect(errorText(new AxiosError('Network Error', 'ERR_NETWORK'))).toBe('Cannot reach the server. Is the backend running?')
  })
})
