import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Download, Search, ChevronRight } from 'lucide-react'
import { api } from '../api/client'
import TopBar from '../components/TopBar'
import StatusBadge from '../components/StatusBadge'

export default function Glossary() {
  const [terms, setTerms] = useState([])
  const [search, setSearch] = useState('')
  const [scheme, setScheme] = useState('all')
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    setLoading(true)
    api.terms.list({ status: 'published', search })
      .then(setTerms)
      .finally(() => setLoading(false))
  }, [search])

  const schemes = ['all', ...new Set(terms.map(t => t.scheme_label).filter(Boolean))]
  const filtered = scheme === 'all' ? terms : terms.filter(t => t.scheme_label === scheme)

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      <TopBar breadcrumb={['Ontology', 'Glossary']} />

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-5xl mx-auto space-y-5">
          {/* Header */}
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-xl font-semibold text-gray-900">Glossary</h1>
              <p className="text-xs text-gray-400 mt-0.5">
                {loading ? '…' : `${filtered.length} published term${filtered.length !== 1 ? 's' : ''}`}
              </p>
            </div>
            <button
              onClick={() => api.terms.exportCsv('published')}
              className="flex items-center gap-2 px-3 py-1.5 bg-white border border-gray-200 rounded-lg text-xs text-gray-600 hover:border-gray-300 transition-colors"
            >
              <Download size={13} /> Export CSV
            </button>
          </div>

          {/* Search + scheme filter */}
          <div className="flex gap-3">
            <div className="relative flex-1 max-w-sm">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-300" />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search terms..."
                className="w-full pl-8 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200 bg-white"
              />
            </div>
            <select
              value={scheme}
              onChange={e => setScheme(e.target.value)}
              className="border border-gray-200 rounded-lg text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-200 bg-white text-gray-600"
            >
              {schemes.map(s => (
                <option key={s} value={s}>{s === 'all' ? 'All schemes' : s}</option>
              ))}
            </select>
          </div>

          {/* Term list */}
          {loading ? (
            <div className="bg-white border border-gray-100 rounded-xl p-12 text-center text-sm text-gray-300">
              Loading...
            </div>
          ) : filtered.length === 0 ? (
            <div className="border border-dashed border-gray-200 rounded-xl p-12 text-center text-sm text-gray-400">
              No published terms found.
            </div>
          ) : (
            <div className="bg-white border border-gray-100 rounded-xl divide-y divide-gray-50">
              {filtered.map(t => (
                <div
                  key={t.term_uri}
                  className="px-5 py-4 hover:bg-gray-50 cursor-pointer transition-colors group flex items-start gap-3"
                  onClick={() => navigate(`/terms/${encodeURIComponent(t.term_uri)}`)}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                      <span className="font-medium text-gray-900 text-sm">{t.preferred_label}</span>
                      {t.scheme_label && (
                        <span className="text-[11px] text-gray-400 bg-gray-100 px-2 py-0.5 rounded font-mono">
                          {t.scheme_label}
                        </span>
                      )}
                      <StatusBadge status={t.lifecycle_status} />
                      {t.approved_by && (
                        <span className="text-[11px] text-gray-300">· {t.approved_by}</span>
                      )}
                    </div>
                    {t.definition && (
                      <p className="text-xs text-gray-500 line-clamp-2 mt-1">{t.definition}</p>
                    )}
                    {t.alt_labels?.length > 0 && (
                      <p className="text-[11px] text-gray-300 mt-1">
                        Also: {t.alt_labels.slice(0, 3).join(', ')}
                      </p>
                    )}
                  </div>
                  <ChevronRight size={14} className="text-gray-200 group-hover:text-gray-400 shrink-0 mt-1 transition-colors" />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
