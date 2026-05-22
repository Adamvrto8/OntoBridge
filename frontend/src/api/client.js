const BASE = '/api'
const API_KEY = import.meta.env.VITE_API_KEY || ''

async function request(path, options = {}) {
  const { timeout = 30000, headers: callerHeaders = {}, ...fetchOptions } = options
  const headers = {
    ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
    ...callerHeaders,
  }
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  try {
    const res = await fetch(`${BASE}${path}`, { ...fetchOptions, headers, signal: controller.signal })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || res.statusText)
    }
    if (res.status === 204) return null
    return res.json()
  } catch (e) {
    if (e.name === 'AbortError') throw new Error('Request timed out — server is still processing, try again in a moment')
    throw e
  } finally {
    clearTimeout(timer)
  }
}

export const api = {
  terms: {
    // Returns PagedResponse: { items, total, limit, offset }
    list: (params = {}) => {
      const { limit = 500, offset = 0, ...rest } = params
      const q = new URLSearchParams({ limit, offset, ...rest }).toString()
      return request(`/terms${q ? '?' + q : ''}`)
    },
    get: (uri) => request(`/terms/${encodeURIComponent(uri)}`),
    transition: (uri, body) =>
      request(`/terms/${encodeURIComponent(uri)}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    edit: (uri, body) =>
      request(`/terms/${encodeURIComponent(uri)}/edit`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    updateRelation: (uri, body) =>
      request(`/terms/${encodeURIComponent(uri)}/relations`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    exportCsv: (status) => {
      const q = status ? `?status=${status}` : ''
      window.open(`${BASE}/terms/export/csv${q}`)
    },
    exportTurtle: (status) => {
      const q = status ? `?status=${status}` : ''
      window.open(`${BASE}/terms/export/turtle${q}`)
    },
  },
  pipeline: {
    run: (formData) =>
      request('/pipeline/run', { method: 'POST', body: formData, timeout: 600000 }),
  },
  audit: {
    // Returns PagedResponse: { items, total, limit, offset }
    list: (limit = 100, offset = 0) => request(`/audit?limit=${limit}&offset=${offset}`),
  },
  stats: {
    get: () => request('/stats'),
    concepts: () => request('/stats/concepts'),
    verbs: () => request('/stats/verbs'),
  },
  graph: {
    get: () => request('/graph'),
  },
}
