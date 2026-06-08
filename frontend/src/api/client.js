const BASE = '/api'
const API_KEY = import.meta.env.VITE_API_KEY || ''

// FastAPI returns errors as { detail: ... } where detail is either a string
// (our own HTTPExceptions) or an array of validation objects (auto-validation,
// 422). Flatten both into a readable string so the UI never shows [object Object].
function extractError(body) {
  if (!body) return null
  const { detail } = body
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map(d => (d?.loc ? `${d.loc.slice(1).join('.')}: ${d.msg}` : d?.msg))
      .filter(Boolean)
      .join('; ')
  }
  if (detail && typeof detail === 'object') return detail.msg || JSON.stringify(detail)
  return typeof body === 'string' ? body : null
}

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
      const err = await res.json().catch(() => null)
      throw new Error(extractError(err) || res.statusText)
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
    // Returns { dawiso_url, term_uri, label }. Requires the term to be PUBLISHED.
    publishDawiso: (uri) =>
      request(`/terms/${encodeURIComponent(uri)}/publish-dawiso`, { method: 'POST' }),
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
}
