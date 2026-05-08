import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCircle, XCircle } from 'lucide-react'
import { api } from '../api/client'
import StatusBadge from '../components/StatusBadge'

export default function Inbox() {
  const [terms, setTerms] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  const load = () => {
    setLoading(true)
    api.terms.list({ status: 'review' })
      .then(setTerms)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const transition = async (uri, newStatus) => {
    try {
      await api.terms.transition(uri, { new_status: newStatus, actor: 'steward' })
      load()
    } catch (e) {
      alert(e.message)
    }
  }

  if (loading) return <p className="p-8 text-gray-400">Loading...</p>
  if (error) return <p className="p-8 text-red-500">{error}</p>

  return (
    <div className="p-8 max-w-4xl">
      <h1 className="text-2xl font-semibold text-gray-900 mb-1">Governance Inbox</h1>
      <p className="text-sm text-gray-500 mb-6">Terms awaiting review and approval.</p>

      {terms.length === 0 ? (
        <div className="border border-dashed border-gray-200 rounded-xl p-12 text-center text-gray-400">
          No terms pending review.
        </div>
      ) : (
        <div className="space-y-3">
          {terms.map(t => (
            <div key={t.term_uri} className="bg-white border border-gray-200 rounded-xl p-5 flex items-start gap-4 hover:border-gray-300 transition-colors">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <button
                    className="font-medium text-gray-900 hover:text-indigo-600 text-left"
                    onClick={() => navigate(`/terms/${encodeURIComponent(t.term_uri)}`)}
                  >
                    {t.preferred_label}
                  </button>
                  <StatusBadge status={t.lifecycle_status} />
                  {t.scheme_label && (
                    <span className="text-xs text-gray-400 bg-gray-50 px-2 py-0.5 rounded">{t.scheme_label}</span>
                  )}
                </div>
                <p className="text-sm text-gray-500 line-clamp-2">{t.definition}</p>
                {t.source_system && (
                  <p className="text-xs text-gray-400 mt-1">Source: {t.source_system}</p>
                )}
              </div>
              <div className="flex gap-2 shrink-0">
                <button
                  onClick={() => transition(t.term_uri, 'published')}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-green-50 text-green-700 hover:bg-green-100 rounded-lg text-sm font-medium transition-colors"
                >
                  <CheckCircle size={14} /> Approve
                </button>
                <button
                  onClick={() => transition(t.term_uri, 'draft')}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-red-50 text-red-700 hover:bg-red-100 rounded-lg text-sm font-medium transition-colors"
                >
                  <XCircle size={14} /> Reject
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
