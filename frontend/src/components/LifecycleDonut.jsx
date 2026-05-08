const COLORS = {
  candidate:  '#B0C4CC',
  draft:      '#7A9BAA',
  review:     '#D93B2B',
  published:  '#1A2528',
  deprecated: '#DCE9EC',
}

export default function LifecycleDonut({ byStatus = {}, total = 0 }) {
  const data = Object.entries(byStatus)
    .filter(([, v]) => v > 0)
    .map(([k, v]) => ({ id: k, name: k.charAt(0).toUpperCase() + k.slice(1), count: v, color: COLORS[k] || '#DCE9EC' }))

  const size = 132, thickness = 16
  const r = (size - thickness) / 2
  const c = size / 2
  const C = 2 * Math.PI * r
  let offset = 0

  return (
    <div className="card">
      <div className="card-h">
        <h3>Lifecycle breakdown</h3>
        <span className="meta mono">{total} terms</span>
      </div>
      <div className="card-b">
        <div className="donut-row">
          <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
            <circle cx={c} cy={c} r={r} fill="none" stroke="#ECF3F5" strokeWidth={thickness} />
            {data.map((d) => {
              const len = total > 0 ? (d.count / total) * C : 0
              const dash = `${len} ${C - len}`
              const off  = -offset
              offset += len
              return (
                <circle key={d.id} cx={c} cy={c} r={r}
                  fill="none" stroke={d.color} strokeWidth={thickness}
                  strokeDasharray={dash} strokeDashoffset={off}
                  transform={`rotate(-90 ${c} ${c})`} />
              )
            })}
            <text x={c} y={c - 2} textAnchor="middle" dominantBaseline="middle"
              style={{ font: "500 22px 'Inter Tight', sans-serif", fill: '#1A2528', fontFeatureSettings: "'tnum'" }}>
              {total}
            </text>
            <text x={c} y={c + 16} textAnchor="middle"
              style={{ font: "400 10px 'JetBrains Mono', monospace", fill: '#7A9BAA', letterSpacing: '0.04em' }}>
              TERMS
            </text>
          </svg>

          <div className="lc-list">
            {data.map((d) => (
              <div className="lc-item" key={d.id}>
                <span className="sw" style={{ background: d.color }} />
                <span className="nm">{d.name}</span>
                <span className="ct">{d.count}</span>
                <span className="pc">{total > 0 ? (d.count / total * 100).toFixed(1) : 0}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
