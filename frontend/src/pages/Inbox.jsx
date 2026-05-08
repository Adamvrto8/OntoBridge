import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { ExternalLink, GitMerge, Plus, CheckCircle, XCircle, ArrowRight } from 'lucide-react'
import { api } from '../api/client'
import TopBar from '../components/TopBar'
import MetricCard from '../components/MetricCard'
import PipelineFunnel from '../components/PipelineFunnel'
import LifecycleDonut from '../components/LifecycleDonut'
import CoverageChart from '../components/CoverageChart'

const SEVERITY = ['All', 'Critical', 'High', 'Medium', 'Low']

const SEV_DOT = {
  Critical: 'bg-red-500',
  High:     'bg-orange-400',
  Medium:   'bg-yellow-400',
  Low:      'bg-blue-400',
}

function severityOf(term) {
  if (!term.definition || term.definition.trim().length === 0) return 'Critical'
  if (term.definition.trim().length < 40) return 'High'
  if (!term.scheme_label) return 'Medium'
  return 'Low'
}

function timeAgo(iso) {
  if (!iso) return null
  const diff = Math.floor((Date.now() - new Date(iso)) / 1000)
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

export default function Inbox() {
  const [reviewTerms, setReviewTerms] = useState([])
  const [stats, setStats] = useState(null)
  const [lastRun, setLastRun] = useState(null)
  const [activeTab, setActiveTab] = useState('All')
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
      setLastRun(latest?.timestamp ? timeAgo(latest.timestamp) : 'recently')
    }).finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const transition = async (uri, newStatus) => {
    try {
      await api.terms.transition(uri, { new_status: newStatus, actor: 'steward' })
      load()
    } catch (e) { alert(e.message) }
  }

  const published  = stats?.by_status?.published ?? 0
  const total      = stats?.total ?? 0
  const reviewCount = stats?.by_status?.review ?? 0
  const draftCount  = stats?.by_status?.draft ?? 0
  const defCoverage = total > 0 ? Math.round((published / total) * 100) : 0

  const sevCounts = SEVERITY.slice(1).reduce((acc, s) => {
    acc[s] = reviewTerms.filter(t => severityOf(t) === s).length
    return acc
  }, {})

  const filtered = activeTab === 'All'
    ? reviewTerms
    : reviewTerms.filter(t => severityOf(t) === activeTab)

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      <TopBar breadcrumb={['Workflow', 'Governance inbox']} />

      <div className="flex-1 overflow-auto p-6 space-y-4">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-xl font-semibold text-gray-900">Governance inbox</h1>
            <p className="text-xs text-gray-400 mt-0.5">Terms awaiting steward action. Sorted by severity, then age.</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => api.terms.exportCsv('review')}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-gray-200 rounded-lg text-gray-600 hover:border-gray-300 bg-white transition-colors"
            >
              <ExternalLink size={12} /> Export turtle
            </button>
            <button className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-gray-200 rounded-lg text-gray-600 hover:border-gray-300 bg-white transition-colors">
              <GitMerge size={12} /> Bulk review
            </button>
            <button
              onClick={() => navigate('/pipeline')}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-gray-900 text-white rounded-lg hover:bg-gray-700 transition-colors"
            >
              <Plus size={12} /> New term
            </button>
          </div>
        </div>

        {/* Metric cards */}
        <div className="grid grid-cols-6 gap-3">
          <MetricCard label="Total nodes"      value={total}              trend={42}        trendLabel="/ 7d"   color="#6366f1" />
          <MetricCard label="Definition Cov."  value={`${defCoverage}%`} trend={1.2}       trendLabel="pt"     color="#6366f1" />
          <MetricCard label="Open issues"      value={reviewCount}        trend={5}         trendLabel="/ 24h"  color="#ef4444" negative />
          <MetricCard label="Pending review"   value={reviewCount}        trend={-3}        trendLabel="/ 24h"  color="#6366f1" />
          <MetricCard label="Audit events 24h" value={stats?.recent_activity ?? 0}          color="#6366f1" />
          <MetricCard label="Pipeline runs"    value={published}          trend={98}        trendLabel="% pass" color="#22c55e" />
        </div>

        {/* Pipeline funnel */}
        <PipelineFunnel total={total} published={published} lastRun={lastRun} />

        {/* 3-column: coverage | donut | graph */}
        <div className="grid grid-cols-3 gap-4">
          <CoverageChart byScheme={stats?.by_scheme ?? {}} />
          <LifecycleDonut byStatus={stats?.by_status ?? {}} total={total} />

          <div className="bg-white border border-gray-100 rounded-xl p-5 flex flex-col">
            <div className="flex items-center justify-between mb-3">
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest">Knowledge graph</p>
              <button
                onClick={() => navigate('/graph')}
                className="text-xs text-indigo-500 hover:text-indigo-700 flex items-center gap-1"
              >
                Open full graph <ArrowRight size={11} />
              </button>
            </div>
            <div className="flex-1 flex items-center justify-center bg-gray-50 rounded-lg min-h-[120px]">
              <div className="text-center">
                <div className="flex items-center justify-center gap-3 mb-2">
                  {[...Array(4)].map((_, i) => (
                    <div key={i} className={`rounded-full ${i === 0 ? 'w-4 h-4 bg-gray-800' : 'w-2.5 h-2.5 bg-gray-300'}`} />
                  ))}
                </div>
                <p className="text-xs text-gray-300">{total} nodes · {Object.keys(stats?.by_scheme ?? {}).length} schemes</p>
              </div>
            </div>
            <div className="flex items-center gap-3 mt-3 pt-3 border-t border-gray-50">
              {[['Hub class', 'bg-gray-800'], ['Concept', 'bg-gray-400'], ['Conflict', 'bg-red-400']].map(([l, c]) => (
                <div key={l} className="flex items-center gap-1.5">
                  <span className={`w-2 h-2 rounded-full ${c}`} />
                  <span className="text-[10px] text-gray-400">{l}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Issues table */}
        <div className="bg-white border border-gray-100 rounded-xl overflow-hidden">
          {/* Tabs */}
          <div className="flex items-center gap-0 border-b border-gray-100 px-5 pt-4">
            {[
              { label: 'Open issues', count: reviewTerms.length, tab: 'All' },
              { label: 'My queue',    count: 0,                  tab: 'queue' },
              { label: 'Watching',    count: 0,                  tab: 'watching' },
            ].map(({ label, count, tab }) => (
              <button
                key={label}
                onClick={() => setActiveTab(tab === 'All' ? 'All' : activeTab)}
                className={`mr-6 pb-3 text-sm font-medium border-b-2 flex items-center gap-1.5 ${
                  activeTab === tab || (tab === 'All' && SEVERITY.includes(activeTab))
                    ? 'border-gray-900 text-gray-900'
                    : 'border-transparent text-gray-400'
                }`}
              >
                {label}
                {count > 0 && (
                  <span className="text-xs bg-gray-100 text-gray-500 rounded px-1.5 py-0.5">{count}</span>
                )}
              </button>
            ))}
          </div>

          {/* Severity filters */}
          <div className="flex items-center gap-2 px-5 py-3 border-b border-gray-50">
            {SEVERITY.map(s => {
              const n = s === 'All' ? reviewTerms.length : sevCounts[s]
              const active = activeTab === s
              return (
                <button
                  key={s}
                  onClick={() => setActiveTab(s)}
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                    active ? 'bg-gray-900 text-white' : 'text-gray-500 hover:bg-gray-50'
                  }`}
                >
                  {s !== 'All' && <span className={`w-1.5 h-1.5 rounded-full ${SEV_DOT[s]}`} />}
                  {s} {n}
                </button>
              )
            })}
          </div>

          {/* Table */}
          {loading ? (
            <p className="px-5 py-8 text-sm text-gray-300">Loading...</p>
          ) : filtered.length === 0 ? (
            <div className="px-5 py-12 text-center text-sm text-gray-300">
              No terms pending review.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest border-b border-gray-50">
                  <th className="px-5 py-2.5 text-left w-20">Severity</th>
                  <th className="px-3 py-2.5 text-left">Term</th>
                  <th className="px-3 py-2.5 text-left">Issue · Rule</th>
                  <th className="px-3 py-2.5 text-left">Lifecycle</th>
                  <th className="px-3 py-2.5 text-left">Domain</th>
                  <th className="px-3 py-2.5 text-left w-28">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.map(t => {
                  const sev = severityOf(t)
                  return (
                    <tr key={t.term_uri} className="hover:bg-gray-50 transition-colors group">
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-1.5">
                          <span className={`w-1.5 h-1.5 rounded-full ${SEV_DOT[sev]}`} />
                          <span className="text-xs text-gray-500">{sev}</span>
                        </div>
                      </td>
                      <td className="px-3 py-3">
                        <button
                          onClick={() => navigate(`/terms/${encodeURIComponent(t.term_uri)}`)}
                          className="text-left hover:text-indigo-600 transition-colors"
                        >
                          <p className="font-medium text-gray-900 text-sm">{t.preferred_label}</p>
                          <p className="text-[10px] text-gray-400 font-mono truncate max-w-[200px]">
                            {t.term_uri.split('/').pop()}
                          </p>
                        </button>
                      </td>
                      <td className="px-3 py-3">
                        <p className="text-xs text-gray-500">Pending governance review</p>
                        <p className="text-[10px] text-gray-300">GOV · {t.scheme_label || 'unclassified'}</p>
                      </td>
                      <td className="px-3 py-3">
                        <div className="flex gap-1 mb-1">
                          {['candidate', 'draft', 'review'].map(s => (
                            <span
                              key={s}
                              className={`w-4 h-1.5 rounded-full ${
                                t.lifecycle_status === s ? 'bg-indigo-400' : 'bg-gray-200'
                              }`}
                            />
                          ))}
                        </div>
                        <p className="text-[10px] text-gray-400">{t.lifecycle_status}</p>
                      </td>
                      <td className="px-3 py-3">
                        <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded font-mono">
                          {t.scheme_label || '—'}
                        </span>
                      </td>
                      <td className="px-3 py-3">
                        <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={() => transition(t.term_uri, 'published')}
                            className="flex items-center gap-1 px-2 py-1 text-xs bg-green-50 text-green-700 hover:bg-green-100 rounded-md transition-colors"
                          >
                            <CheckCircle size={11} /> Approve
                          </button>
                          <button
                            onClick={() => transition(t.term_uri, 'draft')}
                            className="p-1 text-gray-300 hover:text-red-500 rounded transition-colors"
                            title="Reject — send back to draft"
                          >
                            <XCircle size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
