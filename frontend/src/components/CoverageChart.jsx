const THRESHOLD = 80

export default function CoverageChart({ byScheme = {} }) {
  const entries = Object.entries(byScheme)
    .map(([k, v]) => ({ label: k, pct: v }))
    .sort((a, b) => b.pct - a.pct)

  const max = Math.max(...entries.map(e => e.pct), 1)

  return (
    <div className="bg-white border border-gray-100 rounded-xl p-5 flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest">Definition coverage by domain</p>
        <p className="text-xs text-gray-300">threshold {THRESHOLD}%</p>
      </div>
      <div className="flex flex-col gap-2.5 flex-1">
        {entries.length === 0 && (
          <p className="text-xs text-gray-300">No domain data yet.</p>
        )}
        {entries.map(({ label, pct }) => {
          const width = Math.round((pct / max) * 100)
          const below = width < THRESHOLD
          return (
            <div key={label} className="flex items-center gap-3">
              <span className="text-xs text-gray-500 w-24 truncate font-mono">{label}</span>
              <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden relative">
                <div
                  className={`h-full rounded-full ${below ? 'bg-red-400' : 'bg-gray-800'}`}
                  style={{ width: `${width}%` }}
                />
                <div
                  className="absolute top-0 bottom-0 w-px bg-gray-300"
                  style={{ left: `${THRESHOLD}%` }}
                />
              </div>
              <span className={`text-xs font-medium w-8 text-right ${below ? 'text-red-500' : 'text-gray-700'}`}>
                {width}%
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
