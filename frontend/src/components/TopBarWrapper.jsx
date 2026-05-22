import { useState, useEffect, useRef, useCallback } from 'react'
import { useLocation, useNavigate, Link } from 'react-router-dom'
import { api } from '../api/client'

const CRUMBS = {
  '/':         ['Workflow', 'Governance inbox'],
  '/glossary': ['Ontology', 'Glossary'],
  '/graph':    ['Ontology', 'Knowledge graph'],
  '/pipeline': ['Pipeline', 'Run pipeline'],
  '/stats':    ['Pipeline', 'Pipeline stats'],
  '/audit':    ['Pipeline', 'Audit log'],
  '/miro':     ['Tools', 'Miro board'],
  '/terms':    ['Ontology', 'Term detail'],
}

const STATUS_COLOR = {
  published:  'var(--green)',
  review:     'var(--amber)',
  draft:      'var(--slate-d)',
  candidate:  'var(--slate)',
  deprecated: 'var(--red)',
}

export default function TopBarWrapper() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const key = Object.keys(CRUMBS).find(k => pathname === k || (k !== '/' && pathname.startsWith(k))) || '/'
  const [section, page] = CRUMBS[key] || ['', pathname]

  const [query,   setQuery]   = useState('')
  const [results, setResults] = useState([])
  const [open,    setOpen]    = useState(false)
  const [loading, setLoading] = useState(false)
  const [cursor,  setCursor]  = useState(-1)

  const inputRef    = useRef()
  const containerRef = useRef()

  // Debounced search
  const search = useCallback((q) => {
    if (!q.trim()) { setResults([]); setOpen(false); return }
    setLoading(true)
    api.terms.list({ search: q, limit: 8 })
      .then(data => {
        setResults(data.items)
        setOpen(true)
        setCursor(-1)
      })
      .catch(() => setResults([]))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!query.trim()) { setResults([]); setOpen(false); return }
    const t = setTimeout(() => search(query), 280)
    return () => clearTimeout(t)
  }, [query, search])

  // Close on outside click
  useEffect(() => {
    const handler = e => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Close on route change
  useEffect(() => { setOpen(false); setQuery('') }, [pathname])

  const goToTerm = (term) => {
    setOpen(false)
    setQuery('')
    navigate(`/terms?uri=${encodeURIComponent(term.term_uri)}`)
  }

  const handleKey = (e) => {
    if (!open) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setCursor(c => Math.min(c + 1, results.length - 1)) }
    if (e.key === 'ArrowUp')   { e.preventDefault(); setCursor(c => Math.max(c - 1, -1)) }
    if (e.key === 'Enter' && cursor >= 0) goToTerm(results[cursor])
    if (e.key === 'Enter' && cursor < 0 && results.length > 0) goToTerm(results[0])
    if (e.key === 'Escape') { setOpen(false); inputRef.current?.blur() }
  }

  // ⌘K / Ctrl+K focus
  useEffect(() => {
    const handler = e => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        inputRef.current?.focus()
        inputRef.current?.select()
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  return (
    <header className="topbar">
      {/* Breadcrumb */}
      <div className="crumbs">
        <span>{section}</span>
        <span className="sep">/</span>
        <span className="here">{page}</span>
      </div>
      <div className="spacer" />

      {/* Search */}
      <div ref={containerRef} style={{ position: 'relative' }}>
        <div
          className="search"
          style={{ width: 300, background: open ? 'var(--surface)' : undefined, borderColor: open ? 'var(--slate-d)' : undefined }}
        >
          <SearchIcon />
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onFocus={() => query.trim() && setOpen(true)}
            onKeyDown={handleKey}
            placeholder="Search terms, URIs, policies…"
            style={{ background: 'transparent' }}
          />
          {loading
            ? <span style={{ fontSize: 10, color: 'var(--ink-3)' }}>…</span>
            : <span className="kbd">⌘K</span>}
        </div>

        {/* Dropdown */}
        {open && results.length > 0 && (
          <div style={{
            position: 'absolute', top: 'calc(100% + 6px)', left: 0, right: 0,
            background: 'var(--surface)', border: '1px solid var(--ice)',
            borderRadius: 'var(--r-lg)', boxShadow: '0 8px 24px rgba(26,37,40,0.12)',
            zIndex: 100, overflow: 'hidden',
          }}>
            {results.map((t, i) => (
              <button
                key={t.term_uri}
                onMouseDown={() => goToTerm(t)}
                style={{
                  width: '100%', textAlign: 'left', border: 'none', cursor: 'pointer',
                  padding: '9px 12px', display: 'flex', alignItems: 'center', gap: 10,
                  background: i === cursor ? 'var(--ice-50)' : 'var(--surface)',
                  borderBottom: i < results.length - 1 ? '1px solid var(--ice)' : 'none',
                  font: `400 13px var(--font-sans)`,
                  transition: 'background 0.08s',
                }}
                onMouseEnter={() => setCursor(i)}
              >
                <span style={{
                  width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
                  background: STATUS_COLOR[t.lifecycle_status] || 'var(--slate)',
                }} />
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ color: 'var(--ink)', fontWeight: 500 }}>{t.preferred_label}</span>
                  {t.scheme_label && (
                    <span style={{ marginLeft: 8, font: `400 11px var(--font-mono)`, color: 'var(--ink-3)' }}>
                      {t.scheme_label}
                    </span>
                  )}
                </span>
                <span style={{ font: `400 11px var(--font-mono)`, color: 'var(--ink-3)', flexShrink: 0 }}>
                  {t.lifecycle_status}
                </span>
              </button>
            ))}
            <div style={{ padding: '7px 12px', borderTop: '1px solid var(--ice)', display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ font: `400 11px var(--font-sans)`, color: 'var(--ink-3)' }}>
                {results.length} result{results.length !== 1 ? 's' : ''}
              </span>
              <span style={{ font: `400 11px var(--font-sans)`, color: 'var(--ink-3)' }}>
                ↑↓ navigate · ↵ open · Esc close
              </span>
            </div>
          </div>
        )}

        {open && query.trim() && results.length === 0 && !loading && (
          <div style={{
            position: 'absolute', top: 'calc(100% + 6px)', left: 0, right: 0,
            background: 'var(--surface)', border: '1px solid var(--ice)',
            borderRadius: 'var(--r-lg)', padding: '12px',
            boxShadow: '0 8px 24px rgba(26,37,40,0.12)', zIndex: 100,
            font: `400 13px var(--font-sans)`, color: 'var(--ink-3)', textAlign: 'center',
          }}>
            No terms found for "{query}"
          </div>
        )}
      </div>

      {/* Bell */}
      <button className="icon-btn" title="Notifications">
        <BellIcon />
        <span className="alert-dot" />
      </button>
    </header>
  )
}

const SearchIcon = () => (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="7" cy="7" r="4.5"/><path d="m10.5 10.5 3 3"/>
  </svg>
)
const BellIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 11V7a4 4 0 0 1 8 0v4l1.5 1.5h-11L4 11zM6.5 13a1.5 1.5 0 0 0 3 0"/>
  </svg>
)
