import { useEffect, useState } from 'react'
import { api } from '../api/client'

const ACTION_COLOR = {
  published:  'var(--green)',
  approved:   'var(--green)',
  deprecated: 'var(--red)',
  blocked:    'var(--red)',
  drafted:    'var(--slate-d)',
  harvested:  'var(--slate-d)',
  review:     'var(--amber)',
}

function relativeTime(iso) {
  const s = Math.floor((Date.now() - new Date(iso)) / 1000)
  if (s < 60)   return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return new Date(iso).toLocaleDateString()
}

export default function AuditLog() {
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    api.audit.list(200).then(setEntries).finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Audit Log</h1>
          <div className="sub">{entries.length} events recorded · newest first</div>
        </div>
        <div className="actions">
          <button className="btn" onClick={load} disabled={loading}><RefreshIcon /> Refresh</button>
        </div>
      </div>

      {loading ? (
        <p style={{ color: 'var(--ink-3)', fontSize: 13 }}>Loading…</p>
      ) : entries.length === 0 ? (
        <div style={{ padding: '48px 16px', textAlign: 'center', color: 'var(--ink-3)', border: '2px dashed var(--ice)', borderRadius: 'var(--r-lg)' }}>
          No audit events yet. Run the pipeline to generate activity.
        </div>
      ) : (
        <div className="card">
          <table className="issues">
            <colgroup>
              <col style={{ width: 26 }} />
              <col style={{ width: '30%' }} />
              <col style={{ width: 100 }} />
              <col style={{ width: '25%' }} />
              <col style={{ width: 120 }} />
              <col style={{ width: 80 }} />
            </colgroup>
            <thead>
              <tr>
                <th />
                <th>Term</th>
                <th>Action</th>
                <th>Transition</th>
                <th>Actor</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(e => {
                const dot = ACTION_COLOR[e.action] || 'var(--slate)'
                return (
                  <tr key={e.entry_id} style={{ cursor: 'default' }}>
                    <td>
                      <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: dot }} />
                    </td>
                    <td>
                      <div style={{ fontWeight: 500 }}>{e.term_label}</div>
                      <div className="mono" style={{ color: 'var(--ink-3)', marginTop: 2 }}>
                        {e.term_uri.split('/').pop()}
                      </div>
                    </td>
                    <td>
                      <span className="pill" style={{ textTransform: 'capitalize' }}>{e.action}</span>
                    </td>
                    <td style={{ color: 'var(--ink-2)' }}>
                      {e.previous_status && e.new_status
                        ? <span className="mono">{e.previous_status} → {e.new_status}</span>
                        : <span style={{ color: 'var(--ink-3)' }}>—</span>}
                    </td>
                    <td style={{ color: 'var(--ink-2)' }}>{e.actor || '—'}</td>
                    <td className="mono" style={{ color: 'var(--ink-3)' }}>{relativeTime(e.timestamp)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

const RefreshIcon = () => (
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M13.5 8A5.5 5.5 0 1 1 8 2.5a5.5 5.5 0 0 1 3.9 1.6L13.5 2v4h-4l1.6-1.6"/>
  </svg>
)
