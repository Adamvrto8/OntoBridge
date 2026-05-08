import { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { api } from '../api/client'

const STATUS_COLORS = {
  candidate:  '#6366f1',
  draft:      '#3b82f6',
  review:     '#f59e0b',
  published:  '#22c55e',
  deprecated: '#ef4444',
}

export default function Stats() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    api.stats.get().then(setStats).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  if (loading) return <p className="p-8 text-gray-400">Loading...</p>
  if (!stats) return null

  return (
    <div className="p-8 max-w-3xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 mb-1">Pipeline Stats</h1>
          <p className="text-sm text-gray-500">{stats.total} terms total · {stats.recent_activity} audit events</p>
        </div>
        <button onClick={load} className="p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100">
          <RefreshCw size={16} />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-6">
        <Card title="By Status">
          {Object.entries(stats.by_status).map(([s, n]) => (
            <Bar key={s} label={s} value={n} total={stats.total} color={STATUS_COLORS[s] || '#6b7280'} />
          ))}
        </Card>
        <Card title="By Scheme">
          {Object.entries(stats.by_scheme).map(([s, n]) => (
            <Bar key={s} label={s} value={n} total={stats.total} color="#6366f1" />
          ))}
        </Card>
      </div>
    </div>
  )
}

function Card({ title, children }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-4">{title}</p>
      <div className="space-y-3">{children}</div>
    </div>
  )
}

function Bar({ label, value, total, color }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0
  return (
    <div>
      <div className="flex justify-between text-sm mb-1">
        <span className="capitalize text-gray-700">{label}</span>
        <span className="text-gray-400 text-xs">{value} ({pct}%)</span>
      </div>
      <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
    </div>
  )
}
