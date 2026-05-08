import { useEffect, useState } from 'react'
import { api } from '../api/client'

const STATUS_COLORS = {
  candidate: 'var(--slate-d)', draft: 'var(--slate)',
  review: 'var(--amber)', published: 'var(--green)', deprecated: 'var(--red)',
}

export default function Stats() {
  const [stats,   setStats]   = useState(null)
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    api.stats.get().then(setStats).finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Pipeline Stats</h1>
          <div className="sub">
            {stats ? `${stats.total} terms total · ${stats.recent_activity} audit events` : 'Loading…'}
          </div>
        </div>
        <div className="actions">
          <button className="btn" onClick={load} disabled={loading}><RefreshIcon /> Refresh</button>
        </div>
      </div>

      {loading ? (
        <p style={{ color: 'var(--ink-3)', fontSize: 13 }}>Loading…</p>
      ) : !stats ? null : (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--gap)' }}>
          <div className="card">
            <div className="card-h"><h3>By Status</h3></div>
            <div className="card-b">
              <div className="bars">
                {Object.entries(stats.by_status).map(([s, n]) => (
                  <div key={s} className="bar-row">
                    <div className="nm" style={{ textTransform: 'capitalize' }}>{s}</div>
                    <div className="track">
                      <div className="fill" style={{
                        width: `${stats.total > 0 ? Math.round(n / stats.total * 100) : 0}%`,
                        background: STATUS_COLORS[s] || 'var(--ink)',
                      }} />
                    </div>
                    <div className="pc">
                      {n} <span style={{ color: 'var(--ink-3)', fontWeight: 400 }}>
                        ({stats.total > 0 ? Math.round(n / stats.total * 100) : 0}%)
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-h">
              <h3>By Scheme</h3>
              <span className="meta mono">definition coverage %</span>
            </div>
            <div className="card-b">
              {Object.keys(stats.by_scheme).length === 0 ? (
                <p style={{ color: 'var(--ink-3)', fontSize: 12 }}>No scheme data yet.</p>
              ) : (
                <div className="bars">
                  {Object.entries(stats.by_scheme)
                    .sort(([, a], [, b]) => b - a)
                    .map(([s, pct]) => (
                      <div key={s} className={`bar-row${pct < 80 ? ' alert' : ''}`}>
                        <div className="nm">{s}</div>
                        <div className="track">
                          <div className="fill" style={{ width: `${Math.min(pct, 100)}%` }} />
                          <div className="threshold" style={{ left: '80%' }} />
                        </div>
                        <div className="pc">{pct}%</div>
                      </div>
                    ))}
                </div>
              )}
            </div>
          </div>
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
