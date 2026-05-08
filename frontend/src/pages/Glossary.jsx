import { useEffect, useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Download, ExternalLink, Search, ArrowRight } from 'lucide-react'
import { api } from '../api/client'
import TopBar from '../components/TopBar'

function initials(name) {
  if (!name) return '?'
  return name.split(/[.\s_\-@]/).filter(Boolean).map(p => p[0].toUpperCase()).slice(0, 2).join('')
}

const AVATAR_COLORS = [
  'bg-indigo-600', 'bg-violet-600', 'bg-blue-600',
  'bg-emerald-600', 'bg-orange-500', 'bg-rose-600',
]

function Avatar({ name }) {
  const idx = name ? name.charCodeAt(0) % AVATAR_COLORS.length : 0
  return (
    <div className={`w-6 h-6 rounded-full ${AVATAR_COLORS[idx]} text-white text-[10px] font-bold flex items-center justify-center shrink-0`}>
      {initials(name)}
    </div>
  )
}

function SchemePill({ label, className = '' }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono font-medium bg-gray-100 text-gray-600 ${className}`}>
      {label}
    </span>
  )
}

export default function Glossary() {
  const [terms, setTerms]     = useState([])
  const [search, setSearch]   = useState('')
  const [scheme, setScheme]   = useState('all')
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    setLoading(true)
    api.terms.list({ status: 'published' })
      .then(setTerms)
      .finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(() => {
    let result = terms
    if (scheme !== 'all') result = result.filter(t => t.scheme_label === scheme)
    if (search.trim()) {
      const q = search.toLowerCase()
      result = result.filter(t =>
        t.preferred_label?.toLowerCase().includes(q) ||
        t.definition?.toLowerCase().includes(q) ||
        t.term_uri?.toLowerCase().includes(q)
      )
    }
    return result
  }, [terms, scheme, search])

  const schemeCounts = useMemo(() => {
    const map = {}
    terms.forEach(t => {
      const k = t.scheme_label || '—'
      map[k] = (map[k] || 0) + 1
    })
    return map
  }, [terms])

  const schemes = useMemo(() =>
    ['all', ...Object.keys(schemeCounts).sort((a, b) =>
      (schemeCounts[b] || 0) - (schemeCounts[a] || 0)
    )],
    [schemeCounts]
  )

  const schemeCount = scheme === 'all' ? terms.length : (schemeCounts[scheme] || 0)

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      <TopBar breadcrumb={['Ontology', 'Glossary']} />

      <div className="flex-1 overflow-auto">
        <div className="max-w-6xl mx-auto px-8 py-8 space-y-6">

          {/* Header */}
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-semibold text-gray-900 tracking-tight">Glossary</h1>
              <p className="text-sm text-gray-400 mt-1">
                {loading ? 'Loading…' : `${terms.length} published term${terms.length !== 1 ? 's' : ''} across ${Object.keys(schemeCounts).length} concept scheme${Object.keys(schemeCounts).length !== 1 ? 's' : ''}. SKOS prefLabels, definitions, and approvers — the canonical view.`}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button
                onClick={() => window.open('/api/terms/export/csv?status=published')}
                className="flex items-center gap-2 px-3.5 py-2 bg-white border border-gray-200 rounded-lg text-sm text-gray-600 hover:border-gray-300 hover:bg-gray-50 transition-colors"
              >
                <ExternalLink size={13} /> Export turtle
              </button>
              <button
                onClick={() => api.terms.exportCsv('published')}
                className="flex items-center gap-2 px-3.5 py-2 bg-gray-900 text-white rounded-lg text-sm hover:bg-gray-700 transition-colors"
              >
                <Download size={13} /> Export CSV
              </button>
            </div>
          </div>

          {/* Search + count */}
          <div className="flex items-center gap-3">
            <div className="relative max-w-sm w-full">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-300" />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search label, URI, definition…"
                className="w-full pl-9 pr-4 py-2.5 border border-gray-200 rounded-lg text-sm bg-white placeholder-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-transparent transition"
              />
            </div>
            {!loading && (
              <p className="text-sm text-gray-400 ml-auto whitespace-nowrap">
                <span className="font-medium text-gray-700">{filtered.length}</span> / {schemeCount} shown
              </p>
            )}
          </div>

          {/* Scheme chips */}
          {!loading && schemes.length > 1 && (
            <div className="flex flex-wrap gap-2">
              {schemes.map(s => {
                const count = s === 'all' ? terms.length : (schemeCounts[s] || 0)
                const active = scheme === s
                return (
                  <button
                    key={s}
                    onClick={() => setScheme(s)}
                    className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
                      active
                        ? 'bg-gray-900 text-white shadow-sm'
                        : 'bg-white border border-gray-200 text-gray-500 hover:border-gray-300 hover:text-gray-700'
                    }`}
                  >
                    {s === 'all' ? 'All schemes' : (
                      <><span className="font-mono">{s}</span></>
                    )}
                    <span className={`text-[11px] font-semibold tabular-nums ${active ? 'opacity-70' : 'text-gray-400'}`}>
                      {count}
                    </span>
                  </button>
                )
              })}
            </div>
          )}

          {/* Table */}
          {loading ? (
            <div className="bg-white border border-gray-100 rounded-xl p-16 text-center text-sm text-gray-300">
              Loading…
            </div>
          ) : filtered.length === 0 ? (
            <div className="border-2 border-dashed border-gray-200 rounded-xl p-16 text-center text-sm text-gray-400">
              No published terms match your search.
            </div>
          ) : (
            <div className="bg-white border border-gray-100 rounded-xl overflow-hidden shadow-sm">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-100">
                    <th className="px-5 py-3 text-left text-[11px] font-semibold text-gray-400 uppercase tracking-widest w-[30%]">Label</th>
                    <th className="px-4 py-3 text-left text-[11px] font-semibold text-gray-400 uppercase tracking-widest">Definition</th>
                    <th className="px-4 py-3 text-left text-[11px] font-semibold text-gray-400 uppercase tracking-widest w-[12%]">Scheme</th>
                    <th className="px-4 py-3 text-left text-[11px] font-semibold text-gray-400 uppercase tracking-widest w-[14%]">Approved by</th>
                    <th className="px-4 py-3 text-left text-[11px] font-semibold text-gray-400 uppercase tracking-widest w-[8%]">Version</th>
                    <th className="px-4 py-3 w-8" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {filtered.map(t => (
                    <tr
                      key={t.term_uri}
                      onClick={() => navigate(`/terms/${encodeURIComponent(t.term_uri)}`)}
                      className="group hover:bg-gray-50 cursor-pointer transition-colors"
                    >
                      <td className="px-5 py-3.5">
                        <p className="font-semibold text-gray-900 text-sm leading-snug">{t.preferred_label}</p>
                        <p className="text-[11px] text-indigo-400 font-mono mt-0.5 truncate max-w-[220px]">
                          {t.term_uri.split('/').pop() || t.term_uri}
                        </p>
                      </td>
                      <td className="px-4 py-3.5">
                        <p className="text-sm text-gray-500 line-clamp-2 leading-snug">
                          {t.definition || <span className="text-gray-300 italic">No definition</span>}
                        </p>
                      </td>
                      <td className="px-4 py-3.5">
                        {t.scheme_label && <SchemePill label={t.scheme_label} />}
                      </td>
                      <td className="px-4 py-3.5">
                        {t.approved_by ? (
                          <div className="flex items-center gap-2">
                            <Avatar name={t.approved_by} />
                            <span className="text-xs text-gray-500 truncate max-w-[80px]">{t.approved_by}</span>
                          </div>
                        ) : (
                          <span className="text-xs text-gray-300">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3.5">
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-gray-100 text-gray-500">
                          v{t.version}
                        </span>
                      </td>
                      <td className="px-4 py-3.5">
                        <ArrowRight size={14} className="text-gray-200 group-hover:text-gray-400 transition-colors" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
