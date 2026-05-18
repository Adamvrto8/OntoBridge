const BASE = '/api'

async function request(path, options = {}) {
  const { timeout = 30000, ...fetchOptions } = options
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  try {
    const res = await fetch(`${BASE}${path}`, { ...fetchOptions, signal: controller.signal })
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
    list: (params = {}) => {
      const q = new URLSearchParams(params).toString()
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
  },
  pipeline: {
    run: (formData) =>
      request('/pipeline/run', { method: 'POST', body: formData, timeout: 600000 }),
  },
  audit: {
    list: (limit = 100) => request(`/audit?limit=${limit}`),
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
