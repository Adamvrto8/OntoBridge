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
      font: '500 10px var(--font-sans)', flexShrink: 0,
    }}>
      {initials(name)}
    </span>
  )
}

const sel = {
  height: 30, padding: '0 28px 0 10px', appearance: 'none',
  border: '1px solid var(--ice)', borderRadius: 'var(--r)',
  background: `var(--surface) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%238AABB8' stroke-width='1.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E") no-repeat right 8px center`,
  font: '400 12.5px var(--font-sans)', color: 'var(--ink-2)', cursor: 'pointer', outline: 'none',
  minWidth: 120,
}

export default function Glossary() {
  const [terms,      setTerms]      = useState([])
  const [search,     setSearch]     = useState('')
  const [filterScheme,   setFilterScheme]   = useState('')
  const [filterApprover, setFilterApprover] = useState('')
  const [filterVersion,  setFilterVersion]  = useState('')
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    setLoading(true)
    api.terms.list({ status: 'published' }).then(data => setTerms(data.items)).finally(() => setLoading(false))
  }, [])

  // Unique option lists
  const schemes   = useMemo(() => [...new Set(terms.map(t => t.scheme_label).filter(Boolean))].sort(), [terms])
  const approvers = useMemo(() => [...new Set(terms.map(t => t.approved_by).filter(Boolean))].sort(), [terms])
  const versions  = useMemo(() => [...new Set(terms.map(t => t.version))].sort((a, b) => a - b), [terms])

  const filtered = useMemo(() => {
    let r = terms
    if (filterScheme)   r = r.filter(t => t.scheme_label === filterScheme)
    if (filterApprover) r = r.filter(t => t.approved_by  === filterApprover)
    if (filterVersion)  r = r.filter(t => String(t.version) === filterVersion)
    if (search.trim()) {
      const q = search.toLowerCase()
      r = r.filter(t =>
        t.preferred_label?.toLowerCase().includes(q) ||
        t.definition?.toLowerCase().includes(q) ||
        t.term_uri?.toLowerCase().includes(q)
      )
    }
    return r
  }, [terms, search, filterScheme, filterApprover, filterVersion])

  const hasFilters = filterScheme || filterApprover || filterVersion || search.trim()

  const clearFilters = () => {
    setFilterScheme('')
    setFilterApprover('')
    setFilterVersion('')
    setSearch('')
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Glossary</h1>
          <div className="sub">
            {loading ? 'Loading…'
              : `${terms.length} published term${terms.length !== 1 ? 's' : ''} across ${schemes.length} concept scheme${schemes.length !== 1 ? 's' : ''}. SKOS prefLabels, definitions, and approvers — the canonical view.`}
          </div>
        </div>
        <div className="actions">
          <button className="btn" onClick={() => window.open('/api/terms/export/csv?status=published')}>
            <ExtIcon /> Export CSV
          </button>
          <button className="btn primary" onClick={() => api.terms.exportCsv('published')}>
            <DownIcon /> Export CSV
          </button>
        </div>
      </div>

      {/* Search + filters row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 'var(--gap)', flexWrap: 'wrap' }}>
        {/* Search — untouched as requested */}
        <div style={{ position: 'relative', width: 300 }}>
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

        <div style={{ width: 1, height: 20, background: 'var(--ice)' }} />

        {/* Scheme filter */}
        <div style={{ position: 'relative' }}>
          <label style={{ position: 'absolute', top: -16, left: 2, font: '500 10px var(--font-sans)', color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>
            Scheme
          </label>
          <select value={filterScheme} onChange={e => setFilterScheme(e.target.value)} style={{ ...sel, minWidth: 140, color: filterScheme ? 'var(--ink)' : 'var(--ink-3)' }}>
            <option value="">All schemes</option>
            {schemes.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        {/* Approved by filter */}
        <div style={{ position: 'relative' }}>
          <label style={{ position: 'absolute', top: -16, left: 2, font: '500 10px var(--font-sans)', color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>
            Approved by
          </label>
          <select value={filterApprover} onChange={e => setFilterApprover(e.target.value)} style={{ ...sel, minWidth: 130, color: filterApprover ? 'var(--ink)' : 'var(--ink-3)' }}>
            <option value="">All approvers</option>
            {approvers.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
        </div>

        {/* Version filter */}
        <div style={{ position: 'relative' }}>
          <label style={{ position: 'absolute', top: -16, left: 2, font: '500 10px var(--font-sans)', color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>
            Version
          </label>
          <select value={filterVersion} onChange={e => setFilterVersion(e.target.value)} style={{ ...sel, minWidth: 100, color: filterVersion ? 'var(--ink)' : 'var(--ink-3)' }}>
            <option value="">All versions</option>
            {versions.map(v => <option key={v} value={String(v)}>v{v}</option>)}
          </select>
        </div>

        {/* Clear + count */}
        {hasFilters && (
          <button className="btn ghost" style={{ height: 30, padding: '0 10px', fontSize: 12 }} onClick={clearFilters}>
            Clear filters
          </button>
        )}

        {!loading && (
          <span style={{ color: 'var(--ink-3)', fontSize: 12, marginLeft: 'auto' }}>
            <span style={{ color: 'var(--ink)', fontWeight: 500 }}>{filtered.length}</span>
            {' / '}{terms.length} shown
          </span>
        )}
      </div>

      {/* Table */}
      {loading ? (
        <div className="card" style={{ padding: '48px 16px', textAlign: 'center', color: 'var(--ink-3)' }}>Loading…</div>
      ) : filtered.length === 0 ? (
        <div style={{ padding: '48px 16px', textAlign: 'center', color: 'var(--ink-3)', border: '2px dashed var(--ice)', borderRadius: 'var(--r-lg)' }}>
          No terms match your filters.{hasFilters && <> <button className="btn ghost" style={{ marginLeft: 8, height: 26, padding: '0 10px', fontSize: 12 }} onClick={clearFilters}>Clear all</button></>}
        </div>
      ) : (
        <div className="card" style={{ overflow: 'hidden' }}>
          <table className="issues">
            <colgroup>
              <col style={{ width: '27%' }} />
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
                <tr key={t.term_uri} onClick={() => navigate(`/terms?uri=${encodeURIComponent(t.term_uri)}`)}>
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
                    {t.scheme_label
                      ? <span className="scheme-pill" style={filterScheme ? { background: 'var(--ink)', color: '#fff' } : {}}>{t.scheme_label}</span>
                      : <span style={{ color: 'var(--ink-3)' }}>—</span>}
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
        <span>{filtered.length} of {terms.length} published terms shown</span>
        {hasFilters && (
          <span style={{ color: 'var(--ink-3)' }}>
            {filterScheme && `scheme: ${filterScheme}`}
            {filterApprover && ` · approver: ${filterApprover}`}
            {filterVersion && ` · v${filterVersion}`}
          </span>
        )}
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
