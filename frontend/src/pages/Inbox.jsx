import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import MetricCard from '../components/MetricCard'
import PipelineFunnel from '../components/PipelineFunnel'
import LifecycleDonut from '../components/LifecycleDonut'
import CoverageChart from '../components/CoverageChart'

const SEV_FILTERS = ['all', 'crit', 'high', 'med', 'low']
const SEV_LABEL   = { all: 'All', crit: 'Critical', high: 'High', med: 'Medium', low: 'Low' }

function severityOf(term) {
  if (!term.definition || term.definition.trim().length === 0) return 'crit'
  if (term.definition.trim().length < 40) return 'high'
  if (!term.scheme_label) return 'med'
  return 'low'
}

function timeAgo(iso) {
  if (!iso) return null
  const s = Math.floor((Date.now() - new Date(iso)) / 1000)
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  return `${Math.floor(s / 3600)}h ago`
}

const lcOrder = ['candidate', 'draft', 'review', 'published']

export default function Inbox() {
  const [reviewTerms, setReviewTerms] = useState([])
  const [stats,  setStats]  = useState(null)
  const [lastRun, setLastRun] = useState(null)
  const [filter, setFilter] = useState('all')
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([
      api.terms.list({ status: 'review' }),
      api.stats.get(),
      api.audit.list(1),
    ]).then(([terms, s, audit]) => {
      setReviewTerms(terms)
      setStats(s)
      const latest = Array.isArray(audit) ? audit[0] : null
      setLastRun(latest?.timestamp ? timeAgo(latest.timestamp) : null)
    }).finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const transition = async (uri, newStatus) => {
    try {
      await api.terms.transition(uri, { new_status: newStatus, actor: 'steward' })
      load()
    } catch (e) { alert(e.message) }
  }

  const published   = stats?.by_status?.published ?? 0
  const total       = stats?.total ?? 0
  const reviewCount = stats?.by_status?.review ?? 0
  const coverage    = total > 0 ? Math.round(published / total * 100) : 0

  const sevCounts = SEV_FILTERS.slice(1).reduce((a, s) => {
    a[s] = reviewTerms.filter(t => severityOf(t) === s).length; return a
  }, {})

  const filtered = filter === 'all'
    ? reviewTerms
    : reviewTerms.filter(t => severityOf(t) === filter)

  return (
    <>
      {/* Page header */}
      <div className="page-head">
        <div>
          <h1>Governance inbox</h1>
          <div className="sub">Terms awaiting steward action. Sorted by severity, then age.</div>
        </div>
        <div className="actions">
          <button className="btn" onClick={() => api.terms.exportCsv('review')}>
            <ExtIcon /> Export turtle
          </button>
          <button className="btn"><SplitIcon /> Bulk review</button>
          <button className="btn primary" onClick={() => navigate('/pipeline')}>
            <PlusIcon /> New term
          </button>
        </div>
      </div>

      {/* Metric cards */}
      <div className="metrics">
        <MetricCard label="Total nodes"      value={fmt(total)}       delta={`+42 / 7d`}  deltaUp={true} />
        <MetricCard label="Definition cov."  value={`${coverage}%`}  delta={`+1.2 pt`}   deltaUp={true} />
        <MetricCard label="Open issues"      value={fmt(reviewCount)} delta={reviewCount > 0 ? `+${reviewCount} / 24h` : undefined} deltaUp={reviewCount > 0 ? false : undefined} alert />
        <MetricCard label="Pending review"   value={fmt(reviewCount)} delta={`−3 / 24h`}  deltaUp={true} />
        <MetricCard label="Audit events 24h" value={fmt(stats?.recent_activity ?? 0)} delta="stable" />
        <MetricCard label="Pipeline runs"    value={fmt(published)}   delta="98% pass"    deltaUp={true} />
      </div>

      {/* Pipeline funnel */}
      <PipelineFunnel total={total} published={published} lastRun={lastRun} />

      {/* 3-column mid section */}
      <div className="grid-3">
        <CoverageChart byScheme={stats?.by_scheme ?? {}} />
        <LifecycleDonut byStatus={stats?.by_status ?? {}} total={total} />
        <GraphPreviewCard onOpen={() => navigate('/graph')} total={total} schemeCount={Object.keys(stats?.by_scheme ?? {}).length} />
      </div>

      {/* Issues table */}
      <div className="card" style={{ marginBottom: 'var(--gap)' }}>
        <div className="tabs">
          <button className="on">Open issues<span className="ct">{reviewTerms.length}</span></button>
          <button>My queue<span className="ct">—</span></button>
          <button>Watching<span className="ct">—</span></button>
        </div>

        <div className="filters">
          {SEV_FILTERS.map(s => (
            <button
              key={s}
              className={`chip${filter === s ? ' on' : ''}`}
              onClick={() => setFilter(s)}
            >
              {SEV_LABEL[s]}
              <span className="ct">{s === 'all' ? reviewTerms.length : sevCounts[s]}</span>
            </button>
          ))}
        </div>

        {loading ? (
          <div style={{ padding: '32px 16px', color: 'var(--ink-3)', fontSize: 13 }}>Loading…</div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: '48px 16px', textAlign: 'center', color: 'var(--ink-3)', fontSize: 13 }}>
            No terms pending review.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="issues">
              <colgroup>
                <col style={{ width: 110 }} />
                <col style={{ width: '26%' }} />
                <col style={{ width: '22%' }} />
                <col style={{ width: 180 }} />
                <col style={{ width: 110 }} />
                <col style={{ width: 90 }} />
              </colgroup>
              <thead>
                <tr>
                  <th>Severity</th><th>Term</th><th>Issue · rule</th>
                  <th>Lifecycle</th><th>Domain</th><th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(t => {
                  const sev = severityOf(t)
                  const lcIdx = lcOrder.indexOf(t.lifecycle_status ?? 'candidate')
                  return (
                    <tr key={t.term_uri} onClick={() => navigate(`/terms?uri=${encodeURIComponent(t.term_uri)}`)}>
                      <td>
                        <span className={`sev ${sev}`}>
                          <span className="d" />
                          {SEV_LABEL[sev]}
                        </span>
                      </td>
                      <td>
                        <div style={{ fontWeight: 500 }}>{t.preferred_label}</div>
                        <div className="mono" style={{ color: 'var(--ink-3)', marginTop: 2 }}>
                          {t.term_uri.split('/').pop()}
                        </div>
                      </td>
                      <td>
                        <div>Pending governance review</div>
                        <div className="mono" style={{ color: 'var(--ink-3)', marginTop: 2 }}>
                          GOV · {t.scheme_label || 'unclassified'}
                        </div>
                      </td>
                      <td>
                        <span className="lifecycle">
                          {lcOrder.map((s, i) => (
                            <span key={s} className={`b${i <= lcIdx ? ' on' : ''}`} title={s} />
                          ))}
                          <span style={{ marginLeft: 4 }}>{t.lifecycle_status}</span>
                        </span>
                      </td>
                      <td>
                        <span className="scheme-pill">{t.scheme_label || '—'}</span>
                      </td>
                      <td onClick={e => e.stopPropagation()} style={{ textAlign: 'right' }}>
                        <button
                          className="btn ghost" style={{ height: 26, padding: '0 8px' }}
                          onClick={() => transition(t.term_uri, 'published')}
                        >
                          Approve
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="footer-bar">
        <span>Showing {filtered.length} of {reviewTerms.length} open issues · {total} nodes</span>
        <span className="mono">{lastRun ? `last run ${lastRun}` : 'no recent run'}</span>
      </div>
    </>
  )
}

function fmt(n) {
  if (n == null) return '—'
  return Number(n).toLocaleString()
}

function GraphPreviewCard({ onOpen, total, schemeCount }) {
  const nodes = [
    { x: 50,  y: 110, r: 9,  hub: true },
    { x: 130, y: 60,  r: 5 }, { x: 200, y: 95,  r: 5 },
    { x: 175, y: 165, r: 4 }, { x: 95,  y: 190, r: 4 },
    { x: 270, y: 150, r: 4, red: true }, { x: 260, y: 50, r: 3 },
    { x: 320, y: 95,  r: 3 }, { x: 35,  y: 50,  r: 3 }, { x: 380, y: 130, r: 4 },
  ]
  const edges = [[0,1],[0,4],[1,2],[1,3],[2,5],[2,6],[2,7],[0,8],[5,9],[3,4]]

  return (
    <div className="card graph-card">
      <div className="card-h">
        <h3>Knowledge graph</h3>
        <button className="btn ghost" style={{ height: 26, padding: '0 8px', fontSize: 12 }} onClick={onOpen}>
          Open full graph →
        </button>
      </div>
      <div style={{ padding: 12 }}>
        <div className="canvas">
          <svg viewBox="0 0 420 240" preserveAspectRatio="xMidYMid meet">
            {edges.map(([a, b], i) => (
              <line key={i} x1={nodes[a].x} y1={nodes[a].y} x2={nodes[b].x} y2={nodes[b].y}
                stroke="#B0C4CC" strokeWidth="0.8" />
            ))}
            {nodes.map((n, i) => (
              <g key={i}>
                {n.hub && <circle cx={n.x} cy={n.y} r={n.r + 4} fill="none" stroke="#1A2528" strokeWidth="0.9" />}
                <circle cx={n.x} cy={n.y} r={n.r} fill={n.red ? '#D93B2B' : (n.hub ? '#1A2528' : '#7A9BAA')} />
                {n.hub && <circle cx={n.x} cy={n.y} r={n.r - 3} fill="#FFFFFF" />}
              </g>
            ))}
          </svg>
        </div>
        <div style={{ display: 'flex', gap: 16, marginTop: 12, fontSize: 12, color: 'var(--ink-2)' }}>
          {[['#1A2528','Hub class'],['#7A9BAA','Concept'],['#D93B2B','Conflict']].map(([c,l]) => (
            <span key={l} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 8, height: 8, borderRadius: 4, background: c, display: 'inline-block' }} />
              {l}
            </span>
          ))}
          <span style={{ marginLeft: 'auto', color: 'var(--ink-3)' }}>{total} nodes · {schemeCount} schemes</span>
        </div>
      </div>
    </div>
  )
}

const ExtIcon  = () => <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M9 3h4v4M13 3 7 9M7 4H4a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h7a1 1 0 0 0 1-1V9"/></svg>
const SplitIcon = () => <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M3 3v3a3 3 0 0 0 3 3h4a3 3 0 0 1 3 3v1M10 3l3 3-3 3M3 11h4"/></svg>
const PlusIcon  = () => <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"   strokeLinecap="round" strokeLinejoin="round"><path d="M8 3v10M3 8h10"/></svg>
