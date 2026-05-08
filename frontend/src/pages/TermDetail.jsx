import { useEffect, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { api } from '../api/client'

const TRANSITIONS = {
  candidate:  ['draft', 'review'],
  draft:      ['review', 'candidate'],
  review:     ['published', 'draft', 'candidate'],
  published:  ['deprecated', 'review'],
  deprecated: [],
}

const STATUS_PILL = {
  candidate:  '',
  draft:      '',
  review:     'amber',
  published:  'green',
  deprecated: 'red',
}

const lcOrder = ['candidate', 'draft', 'review', 'published']

export default function TermDetail() {
  const [searchParams] = useSearchParams()
  const uri = searchParams.get('uri')
  const navigate = useNavigate()
  const [term,    setTerm]    = useState(null)
  const [error,   setError]   = useState(null)
  const [loading, setLoading] = useState(true)
  const [actor,   setActor]   = useState('')

  const load = () => {
    if (!uri) { setLoading(false); return }
    setLoading(true); setError(null)
    api.terms.get(uri)
      .then(setTerm)
      .catch(e => setError(e.message || 'Failed to load term'))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [uri])

  const transition = async (newStatus) => {
    try {
      await api.terms.transition(uri, { new_status: newStatus, actor: actor || 'steward' })
      load()
    } catch (e) { alert(e.message) }
  }

  if (!uri)    return <p style={{ color: 'var(--ink-3)', fontSize: 13 }}>No term URI provided.</p>
  if (loading) return <p style={{ color: 'var(--ink-3)', fontSize: 13 }}>Loading…</p>
  if (error)   return (
    <div style={{ padding: '16px', background: 'var(--red-bg)', borderRadius: 'var(--r)', color: 'var(--red)', fontSize: 13, maxWidth: 500 }}>
      <strong>Could not load term</strong><br />{error}<br />
      <span style={{ color: 'var(--ink-3)', fontSize: 11, marginTop: 4, display: 'block' }}>URI: {uri}</span>
    </div>
  )
  if (!term)   return <p style={{ color: 'var(--ink-3)', fontSize: 13 }}>Term not found.</p>

  const nextStatuses = TRANSITIONS[term.lifecycle_status] || []
  const lcIdx = lcOrder.indexOf(term.lifecycle_status)

  return (
    <>
      <div className="page-head">
        <div>
          <button
            className="btn ghost"
            onClick={() => navigate(-1)}
            style={{ marginBottom: 8, paddingLeft: 0 }}
          >
            ← Back
          </button>
          <h1>{term.preferred_label}</h1>
          {term.scheme_label && (
            <div className="sub" style={{ marginTop: 4 }}>
              <span className="scheme-pill">{term.scheme_label}</span>
            </div>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span className="lifecycle">
            {lcOrder.map((s, i) => (
              <span key={s} className={`b${i <= lcIdx ? ' on' : ''}`} title={s} />
            ))}
            <span style={{ marginLeft: 6 }}>{term.lifecycle_status}</span>
          </span>
          <span className={`pill ${STATUS_PILL[term.lifecycle_status] || ''}`}>
            {term.lifecycle_status}
          </span>
        </div>
      </div>

      <div style={{ maxWidth: 800, display: 'flex', flexDirection: 'column', gap: 'var(--gap)' }}>

        {/* Main card */}
        <div className="card">
          <div className="card-h">
            <h3>Definition</h3>
            <span className="meta mono">{term.term_uri.split('/').pop()}</span>
          </div>
          <div className="card-b">
            <p style={{ color: 'var(--ink)', lineHeight: 1.6, fontSize: 14 }}>
              {term.definition || <span style={{ color: 'var(--ink-3)', fontStyle: 'italic' }}>No definition available.</span>}
            </p>

            {term.alt_labels?.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <div style={{ font: '500 10.5px var(--font-sans)', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-3)', marginBottom: 8 }}>
                  Also known as
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {term.alt_labels.map(l => <span key={l} className="pill">{l}</span>)}
                </div>
              </div>
            )}

            {term.business_rules?.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <div style={{ font: '500 10.5px var(--font-sans)', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-3)', marginBottom: 8 }}>
                  Business rules
                </div>
                {term.business_rules.map((r, i) => (
                  <div key={i} style={{
                    display: 'flex', gap: 10, padding: '6px 0',
                    borderBottom: i < term.business_rules.length - 1 ? '1px solid var(--ice)' : 0,
                    fontSize: 13, color: 'var(--ink-2)',
                  }}>
                    <span style={{ color: 'var(--slate)', flexShrink: 0 }}>·</span> {r}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Taxonomy */}
        {(term.broader_label || term.scheme_label) && (
          <div className="card">
            <div className="card-h"><h3>Taxonomy</h3></div>
            <div className="card-b" style={{ display: 'grid', gridTemplateColumns: '140px 1fr', gap: '8px 16px', fontSize: 13 }}>
              {term.broader_label && (<>
                <span style={{ color: 'var(--ink-3)' }}>Broader concept</span>
                <span className="mono" style={{ color: 'var(--ink-2)' }}>{term.broader_label}</span>
              </>)}
              {term.scheme_label && (<>
                <span style={{ color: 'var(--ink-3)' }}>Scheme</span>
                <span className="scheme-pill">{term.scheme_label}</span>
              </>)}
            </div>
          </div>
        )}

        {/* Semantic relations */}
        {term.relations?.length > 0 && (
          <div className="card">
            <div className="card-h"><h3>Semantic relations</h3><span className="meta mono">{term.relations.length}</span></div>
            <div style={{ padding: '4px 0' }}>
              {term.relations.map((r, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px',
                  borderBottom: i < term.relations.length - 1 ? '1px solid var(--ice)' : 0,
                  fontSize: 13,
                }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--green)', flexShrink: 0 }} />
                  <span className="mono" style={{ color: 'var(--slate-d)' }}>{r.predicate}</span>
                  <span style={{ color: 'var(--ink-3)' }}>→</span>
                  <span style={{ color: 'var(--ink)', fontWeight: 500 }}>{r.object_label}</span>
                  {r.object_uri && (
                    <span className="mono" style={{ color: 'var(--ink-3)', fontSize: 11 }}>{r.object_uri.split('/').pop()}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Metadata */}
        <div className="card">
          <div className="card-h"><h3>Metadata</h3></div>
          <div className="card-b">
            <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr', gap: '8px 16px', fontSize: 13 }}>
              {[
                ['URI',         <span className="mono" style={{ color: 'var(--ink-2)' }}>{term.term_uri}</span>],
                ['Scheme',      term.scheme_label || '—'],
                ['Approved by', term.approved_by  || '—'],
                ['Source',      term.source_system || '—'],
                ['Document',    term.document_id  || '—'],
                ['Version',     <span className="pill">v{term.version}</span>],
              ].map(([k, v]) => (
                <>
                  <span key={`k-${k}`} style={{ color: 'var(--ink-3)' }}>{k}</span>
                  <span key={`v-${k}`} style={{ color: 'var(--ink)' }}>{v}</span>
                </>
              ))}
            </div>
          </div>
        </div>

        {/* Transition */}
        {nextStatuses.length > 0 && (
          <div className="card">
            <div className="card-h"><h3>Transition status</h3></div>
            <div className="card-b" style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <input
                value={actor}
                onChange={e => setActor(e.target.value)}
                placeholder="Your name (optional)"
                style={{
                  height: 32, padding: '0 10px', border: '1px solid var(--ice)',
                  borderRadius: 'var(--r)', background: 'var(--surface)',
                  font: '400 13px var(--font-sans)', color: 'var(--ink)', outline: 'none',
                }}
              />
              {nextStatuses.map(s => (
                <button key={s} className="btn" onClick={() => transition(s)}
                  style={{ textTransform: 'capitalize' }}>
                  → {s}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  )
}
