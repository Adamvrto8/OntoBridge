const STAGES = [
  { key: 'harvest',    label: 'Harvest',    sub: 'policies + catalogs' },
  { key: 'mapping',    label: 'Mapping',    sub: 'fibo + dedupe' },
  { key: 'taxonomy',   label: 'Taxonomy',   sub: 'skos placement' },
  { key: 'relations',  label: 'Relations',  sub: 'verb resolution' },
  { key: 'governance', label: 'Governance', sub: 'rule check' },
  { key: 'writer',     label: 'Writer',     sub: 'turtle published' },
]

const DOT_COLORS = [
  'bg-gray-400', 'bg-blue-400', 'bg-indigo-400',
  'bg-purple-400', 'bg-orange-400', 'bg-green-500',
]

export default function PipelineFunnel({ total = 0, published = 0, lastRun = null }) {
  const counts = estimateFunnel(total, published)
  return (
    <div className="bg-white border border-gray-100 rounded-xl px-5 py-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-gray-400">
          Pipeline · {lastRun ? `last run ${lastRun}` : 'no recent run'}
        </p>
        <p className="text-xs text-gray-400">{counts[5]} · {published} published</p>
      </div>
      <div className="grid grid-cols-6 gap-3">
        {STAGES.map((s, i) => (
          <div key={s.key} className="flex flex-col gap-1">
            <div className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full ${DOT_COLORS[i]}`} />
              <span className="text-xs font-medium text-gray-600">{s.label}</span>
            </div>
            <p className="text-xl font-semibold text-gray-900 pl-3.5">{counts[i]}</p>
            <p className="text-[10px] text-gray-400 pl-3.5">{s.sub}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

function estimateFunnel(total, published) {
  if (total === 0) return [0, 0, 0, 0, 0, 0]
  const factors = [1, 0.92, 0.84, 0.79, 0.75, published / total]
  return factors.map(f => Math.round(total * f))
}
