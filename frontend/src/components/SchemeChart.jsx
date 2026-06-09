export default function SchemeChart({ byScheme = {} }) {
  const entries = Object.entries(byScheme)
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count)
  const max = entries.reduce((m, e) => Math.max(m, e.count), 0) || 1
  const total = entries.reduce((s, e) => s + e.count, 0)

  return (
    <div className="card">
      <div className="card-h">
        <h3>Terms by domain</h3>
        <span className="meta mono">{total} term{total !== 1 ? 's' : ''}</span>
      </div>
      <div className="card-b">
        {entries.length === 0 ? (
          <p style={{ color: 'var(--ink-3)', fontSize: 12 }}>No terms yet.</p>
        ) : (
          <div className="bars">
            {entries.map(({ label, count }) => (
              <div key={label} className="bar-row">
                <div className="nm">{label}</div>
                <div className="track">
                  <div className="fill" style={{ width: `${Math.round(count / max * 100)}%` }} />
                </div>
                <div className="pc">{count}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
