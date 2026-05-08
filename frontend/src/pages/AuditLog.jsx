import { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { api } from '../api/client'

export default function AuditLog() {
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    api.audit.list().then(setEntries).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  return (
    <div className="p-8 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 mb-1">Audit Log</h1>
          <p className="text-sm text-gray-500">{entries.length} events recorded</p>
        </div>
        <button onClick={load} className="p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100">
          <RefreshCw size={16} />
        </button>
      </div>

      {loading ? (
        <p className="text-gray-400">Loading...</p>
      ) : entries.length === 0 ? (
        <div className="border border-dashed border-gray-200 rounded-xl p-12 text-center text-gray-400">
          No audit events yet.
        </div>
      ) : (
        <div className="bg-white border border-gray-200 rounded-xl divide-y divide-gray-100">
          {entries.map(e => (
            <div key={e.entry_id} className="px-5 py-3.5 flex items-center gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm text-gray-900">{e.term_label}</span>
                  <span className="text-xs px-2 py-0.5 rounded bg-gray-100 text-gray-600 capitalize">{e.action}</span>
                  {e.previous_status && e.new_status && (
                    <span className="text-xs text-gray-400">{e.previous_status} → {e.new_status}</span>
                  )}
                </div>
                {e.actor && <p className="text-xs text-gray-400 mt-0.5">by {e.actor}</p>}
              </div>
              <span className="text-xs text-gray-400 shrink-0">
                {new Date(e.timestamp).toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
