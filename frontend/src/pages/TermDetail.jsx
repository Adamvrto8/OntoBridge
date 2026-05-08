import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { api } from '../api/client'
import StatusBadge from '../components/StatusBadge'

const TRANSITIONS = {
  candidate: ['draft', 'review'],
  draft:     ['review', 'candidate'],
  review:    ['published', 'draft', 'candidate'],
  published: ['deprecated', 'review'],
  deprecated: [],
}

export default function TermDetail() {
  const { '*': uri } = useParams()
  const navigate = useNavigate()
  const [term, setTerm] = useState(null)
  const [loading, setLoading] = useState(true)
  const [actor, setActor] = useState('')

  const load = () => {
    setLoading(true)
    api.terms.get(decodeURIComponent(uri))
      .then(setTerm)
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [uri])

  const transition = async (newStatus) => {
    try {
      await api.terms.transition(decodeURIComponent(uri), { new_status: newStatus, actor: actor || 'steward' })
      load()
    } catch (e) { alert(e.message) }
  }

  if (loading) return <p className="p-8 text-gray-400">Loading...</p>
  if (!term) return <p className="p-8 text-red-500">Term not found.</p>

  const nextStatuses = TRANSITIONS[term.lifecycle_status] || []

  return (
    <div className="p-8 max-w-3xl">
      <button onClick={() => navigate(-1)} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 mb-6">
        <ArrowLeft size={15} /> Back
      </button>

      <div className="bg-white border border-gray-200 rounded-xl p-6 mb-4">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <h1 className="text-xl font-semibold text-gray-900">{term.preferred_label}</h1>
            {term.scheme_label && <p className="text-sm text-gray-400 mt-0.5">{term.scheme_label}</p>}
          </div>
          <StatusBadge status={term.lifecycle_status} />
        </div>

        <p className="text-sm text-gray-700 leading-relaxed mb-5">{term.definition}</p>

        {term.alt_labels?.length > 0 && (
          <div className="mb-4">
            <p className="text-xs font-medium text-gray-500 mb-1.5">Also known as</p>
            <div className="flex flex-wrap gap-1.5">
              {term.alt_labels.map(l => (
                <span key={l} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded">{l}</span>
              ))}
            </div>
          </div>
        )}

        {term.business_rules?.length > 0 && (
          <div className="mb-4">
            <p className="text-xs font-medium text-gray-500 mb-1.5">Business rules</p>
            <ul className="space-y-1">
              {term.business_rules.map((r, i) => (
                <li key={i} className="text-sm text-gray-600 flex gap-2">
                  <span className="text-gray-300 shrink-0">·</span> {r}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="grid grid-cols-2 gap-4 text-xs text-gray-400 border-t border-gray-100 pt-4 mt-2">
          {term.approved_by && <span>Approved by: <span className="text-gray-600">{term.approved_by}</span></span>}
          {term.source_system && <span>Source: <span className="text-gray-600">{term.source_system}</span></span>}
          {term.document_id && <span>Document: <span className="text-gray-600">{term.document_id}</span></span>}
          <span>Version: <span className="text-gray-600">v{term.version}</span></span>
        </div>
      </div>

      {nextStatuses.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <p className="text-xs font-medium text-gray-500 mb-3">Transition status</p>
          <div className="flex items-center gap-3 flex-wrap">
            <input
              value={actor}
              onChange={e => setActor(e.target.value)}
              placeholder="Your name (optional)"
              className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
            {nextStatuses.map(s => (
              <button
                key={s}
                onClick={() => transition(s)}
                className="px-4 py-1.5 rounded-lg text-sm font-medium border transition-colors capitalize
                  border-gray-200 text-gray-700 hover:border-indigo-300 hover:text-indigo-700 hover:bg-indigo-50"
              >
                → {s}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
