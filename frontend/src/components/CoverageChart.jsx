export default function CoverageChart({ byScheme = {} }) {
  const entries = Object.entries(byScheme)
    .map(([k, v]) => ({ label: k, pct: v }))
    .sort((a, b) => b.pct - a.pct)

  return (
    <div className="card">
      <div className="card-h">
        <h3>Definition coverage by domain</h3>
        <span className="meta mono">threshold 80%</span>
      </div>
      <div className="card-b">
        {entries.length === 0 ? (
          <p style={{ color: 'var(--ink-3)', fontSize: 12 }}>No domain data yet.</p>
        ) : (
          <div className="bars">
            {entries.map(({ label, pct }) => (
              <div key={label} className={`bar-row${pct < 80 ? ' alert' : ''}`}>
                <div className="nm">{label}</div>
                <div className="track">
                  <div className="fill" style={{ width: `${Math.min(pct, 100)}%` }} />
                  <div className="threshold" style={{ left: '80%' }} />
                </div>
                <div className="pc">{pct}%</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
