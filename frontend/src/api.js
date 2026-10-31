// Base URL for the backend. Empty in development (Vite proxies /api to FastAPI);
// set VITE_API_BASE_URL at build time when the API lives on another host.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

// The access token lives in sessionStorage, so it is gone when the tab closes.
const TOKEN_KEY = 'hh_access_token'

export function getToken() {
  return sessionStorage.getItem(TOKEN_KEY)
}

function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY)
}

// Calls the API and throws an Error carrying the backend's message (and code) on failure.
async function request(path, { method = 'GET', body, auth = false } = {}) {
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (auth && getToken()) headers.Authorization = `Bearer ${getToken()}`

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (response.status === 204) return null

  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    if (response.status === 401 && auth) clearToken()
    const error = new Error(data.message ?? `Request failed with status ${response.status}`)
    error.code = data.code
    error.status = response.status
    throw error
  }
  return data
}

export function getHealth() {
  return request('/api/v1/health')
}

export async function signIn(email, password) {
  const data = await request('/api/v1/auth/login', {
    method: 'POST',
    body: { email, password },
  })
  sessionStorage.setItem(TOKEN_KEY, data.access_token)
  return data.user
}

export function getCurrentUser() {
  return request('/api/v1/auth/me', { auth: true })
}

export async function signOut() {
  try {
    await request('/api/v1/auth/logout', { method: 'POST', auth: true })
  } finally {
    clearToken()
  }
}
