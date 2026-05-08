import { useEffect, useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'

function initials(name) {
  if (!name) return '?'
  return name.split(/[.\s_\-@]/).filter(Boolean).map(p => p[0].toUpperCase()).slice(0, 2).join('')
}

const AV_COLORS = ['#6366f1','#7c3aed','#2563eb','#059669','#d97706','#dc2626']

function Avatar({ name }) {
  const color = AV_COLORS[(name?.charCodeAt(0) ?? 0) % AV_COLORS.length]
  return (
    <span style={{
      display: 'inline-grid', placeItems: 'center',
      width: 22, height: 22, borderRadius: '50%',
      background: color, color: '#fff',
      font: `500 10px var(--font-sans)`, flexShrink: 0,
    }}>
      {initials(name)}
    </span>
  )
}

export default function Glossary() {
  const [terms,  setTerms]  = useState([])
  const [search, setSearch] = useState('')
  const [scheme, setScheme] = useState('all')
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    setLoading(true)
    api.terms.list({ status: 'published' }).then(setTerms).finally(() => setLoading(false))
  }, [])

  const schemeCounts = useMemo(() => {
    const m = {}
    terms.forEach(t => { const k = t.scheme_label || '—'; m[k] = (m[k] || 0) + 1 })
    return m
  }, [terms])

  const schemes = useMemo(() =>
    ['all', ...Object.keys(schemeCounts).sort((a, b) => schemeCounts[b] - schemeCounts[a])],
    [schemeCounts])

  const filtered = useMemo(() => {
    let r = scheme === 'all' ? terms : terms.filter(t => t.scheme_label === scheme)
    if (search.trim()) {
      const q = search.toLowerCase()
      r = r.filter(t =>
        t.preferred_label?.toLowerCase().includes(q) ||
        t.definition?.toLowerCase().includes(q) ||
        t.term_uri?.toLowerCase().includes(q)
      )
    }
    return r
  }, [terms, scheme, search])

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Glossary</h1>
          <div className="sub">
            {loading ? 'Loading…'
              : `${terms.length} published term${terms.length !== 1 ? 's' : ''} across ${Object.keys(schemeCounts).length} concept scheme${Object.keys(schemeCounts).length !== 1 ? 's' : ''}. SKOS prefLabels, definitions, and approvers — the canonical view.`}
          </div>
        </div>
        <div className="actions">
          <button className="btn" onClick={() => window.open('/api/terms/export/csv?status=published')}>
            <ExtIcon /> Export turtle
          </button>
          <button className="btn primary" onClick={() => api.terms.exportCsv('published')}>
            <DownIcon /> Export CSV
          </button>
        </div>
      </div>

      {/* Search + count */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 'var(--gap)' }}>
        <div style={{ position: 'relative', maxWidth: 340, flex: 1 }}>
          <SearchIcon />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search label, URI, definition…"
            style={{
              width: '100%', height: 32, paddingLeft: 32, paddingRight: 12,
              border: '1px solid var(--ice)', borderRadius: 'var(--r)',
              background: 'var(--surface)', font: '400 13px var(--font-sans)',
              color: 'var(--ink)', outline: 'none',
            }}
            onFocus={e => e.target.style.borderColor = 'var(--slate-d)'}
            onBlur={e  => e.target.style.borderColor = 'var(--ice)'}
          />
        </div>
        {!loading && (
          <span style={{ color: 'var(--ink-3)', fontSize: 12, marginLeft: 'auto' }}>
            <span style={{ color: 'var(--ink)', fontWeight: 500 }}>{filtered.length}</span>
            {' / '}{scheme === 'all' ? terms.length : (schemeCounts[scheme] || 0)} shown
          </span>
        )}
      </div>

      {/* Scheme chips */}
      {!loading && schemes.length > 1 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 'var(--gap)' }}>
          {schemes.map(s => {
            const count = s === 'all' ? terms.length : (schemeCounts[s] || 0)
            const on = scheme === s
            return (
              <button
                key={s}
                className={`chip${on ? ' on' : ''}`}
                onClick={() => setScheme(s)}
              >
                {s === 'all' ? 'All schemes' : <span className="mono">{s}</span>}
                <span className="ct">{count}</span>
              </button>
            )
          })}
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="card" style={{ padding: '48px 16px', textAlign: 'center', color: 'var(--ink-3)' }}>Loading…</div>
      ) : filtered.length === 0 ? (
        <div style={{ padding: '48px 16px', textAlign: 'center', color: 'var(--ink-3)', border: '2px dashed var(--ice)', borderRadius: 'var(--r-lg)' }}>
          No published terms match your search.
        </div>
      ) : (
        <div className="card" style={{ overflow: 'hidden' }}>
          <table className="issues">
            <colgroup>
              <col style={{ width: '28%' }} />
              <col />
              <col style={{ width: 130 }} />
              <col style={{ width: 160 }} />
              <col style={{ width: 70 }} />
              <col style={{ width: 36 }} />
            </colgroup>
            <thead>
              <tr>
                <th>Label</th><th>Definition</th><th>Scheme</th>
                <th>Approved by</th><th>Version</th><th />
              </tr>
            </thead>
            <tbody>
              {filtered.map(t => (
                <tr key={t.term_uri} onClick={() => navigate(`/terms/${encodeURIComponent(t.term_uri)}`)}>
                  <td>
                    <div style={{ fontWeight: 500 }}>{t.preferred_label}</div>
                    <div className="mono" style={{ color: 'var(--ink-3)', marginTop: 2 }}>
                      {t.term_uri.split('/').pop() || t.term_uri}
                    </div>
                  </td>
                  <td style={{ color: 'var(--ink-2)' }}>
                    {t.definition
                      ? <span style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{t.definition}</span>
                      : <span style={{ color: 'var(--ink-3)', fontStyle: 'italic' }}>No definition</span>}
                  </td>
                  <td>
                    {t.scheme_label && <span className="scheme-pill">{t.scheme_label}</span>}
                  </td>
                  <td>
                    {t.approved_by
                      ? <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <Avatar name={t.approved_by} />
                          <span style={{ fontSize: 12, color: 'var(--ink-2)' }}>{t.approved_by}</span>
                        </span>
                      : <span style={{ color: 'var(--ink-3)' }}>—</span>}
                  </td>
                  <td><span className="pill">v{t.version}</span></td>
                  <td style={{ color: 'var(--ink-3)' }}>→</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="footer-bar">
        <span>{filtered.length} of {terms.length} terms shown</span>
      </div>
    </>
  )
}

const SearchIcon = () => (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="var(--ink-3)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
       style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }}>
    <circle cx="7" cy="7" r="4.5"/><path d="m10.5 10.5 3 3"/>
  </svg>
)
const ExtIcon = () => <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M9 3h4v4M13 3 7 9M7 4H4a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h7a1 1 0 0 0 1-1V9"/></svg>
const DownIcon = () => <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 2v9m-3-3 3 3 3-3M3 13.5h10"/></svg>
