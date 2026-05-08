import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Download, Search } from 'lucide-react'
import { api } from '../api/client'
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
    <div className="p-8 max-w-5xl">
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 mb-1">Glossary</h1>
          <p className="text-sm text-gray-500">{filtered.length} published term{filtered.length !== 1 ? 's' : ''}</p>
        </div>
        <button
          onClick={() => api.terms.exportCsv('published')}
          className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-lg text-sm text-gray-600 hover:border-gray-300 transition-colors"
        >
          <Download size={15} /> Export CSV
        </button>
      </div>

      <div className="flex gap-3 mb-5">
        <div className="relative flex-1 max-w-sm">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search terms..."
            className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
        </div>
        <select
          value={scheme}
          onChange={e => setScheme(e.target.value)}
          className="border border-gray-200 rounded-lg text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-white"
        >
          {schemes.map(s => <option key={s} value={s}>{s === 'all' ? 'All schemes' : s}</option>)}
        </select>
      </div>

      {loading ? (
        <p className="text-gray-400">Loading...</p>
      ) : filtered.length === 0 ? (
        <div className="border border-dashed border-gray-200 rounded-xl p-12 text-center text-gray-400">
          No published terms found.
        </div>
      ) : (
        <div className="bg-white border border-gray-200 rounded-xl divide-y divide-gray-100">
          {filtered.map(t => (
            <div
              key={t.term_uri}
              className="px-5 py-4 hover:bg-gray-50 cursor-pointer transition-colors"
              onClick={() => navigate(`/terms/${encodeURIComponent(t.term_uri)}`)}
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="font-medium text-gray-900">{t.preferred_label}</span>
                {t.scheme_label && (
                  <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded">{t.scheme_label}</span>
                )}
                {t.approved_by && (
                  <span className="text-xs text-gray-400">· {t.approved_by}</span>
                )}
              </div>
              <p className="text-sm text-gray-500 line-clamp-2">{t.definition}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
