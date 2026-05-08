export default function Graph() {
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Knowledge Graph</h1>
          <div className="sub">Interactive term relationship graph — served from the Streamlit dashboard.</div>
        </div>
        <div className="actions">
          <a href="http://localhost:8501" target="_blank" rel="noopener noreferrer" className="btn primary">
            <ExtIcon /> Open in Streamlit
          </a>
        </div>
      </div>

      <div className="card">
        <div className="card-h">
          <h3>Graph preview</h3>
          <span className="meta mono">static · connect backend for live</span>
        </div>
        <div style={{ padding: 12 }}>
          <div style={{
            height: 360, borderRadius: 'var(--r)', position: 'relative', overflow: 'hidden',
            background: `radial-gradient(circle at 20% 30%, rgba(176,196,204,0.18), transparent 50%),
                         radial-gradient(circle at 80% 70%, rgba(220,233,236,0.5), transparent 60%),
                         var(--ice-50)`,
          }}>
            <svg viewBox="0 0 900 360" preserveAspectRatio="xMidYMid meet"
                 style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
              <GraphNodes />
            </svg>
          </div>

          <div style={{ display: 'flex', gap: 20, marginTop: 14, fontSize: 12, color: 'var(--ink-2)', alignItems: 'center' }}>
            {[['#1A2528','Hub class'],['#7A9BAA','Concept'],['#D93B2B','Conflict']].map(([c, l]) => (
              <span key={l} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ width: 8, height: 8, borderRadius: 4, background: c, flexShrink: 0 }} />{l}
              </span>
            ))}
            <span style={{ marginLeft: 'auto', color: 'var(--ink-3)' }}>
              Open Streamlit at <span className="mono">localhost:8501</span> for the interactive version
            </span>
          </div>
        </div>
      </div>
    </>
  )
}

function GraphNodes() {
  const nodes = [
    { x: 120,  y: 180, r: 14, hub: true,  label: 'Customer' },
    { x: 280,  y: 90,  r: 8,             label: 'RetailCustomer' },
    { x: 420,  y: 140, r: 7,             label: 'PremiumCustomer' },
    { x: 380,  y: 260, r: 6,             label: 'JointAccountHolder' },
    { x: 210,  y: 290, r: 7,             label: 'Account' },
    { x: 560,  y: 220, r: 7,  red: true,  label: 'Loan (conflict)' },
    { x: 540,  y: 80,  r: 5 },
    { x: 680,  y: 130, r: 5 },
    { x: 90,   y: 80,  r: 5 },
    { x: 760,  y: 240, r: 6 },
    { x: 650,  y: 310, r: 5 },
    { x: 300,  y: 310, r: 5 },
  ]
  const edges = [[0,1],[0,4],[0,8],[1,2],[1,3],[2,5],[2,6],[2,7],[3,4],[3,11],[5,9],[5,10]]

  return (
    <>
      {edges.map(([a, b], i) => (
        <line key={i} x1={nodes[a].x} y1={nodes[a].y} x2={nodes[b].x} y2={nodes[b].y}
          stroke="#B0C4CC" strokeWidth="1" />
      ))}
      {nodes.map((n, i) => (
        <g key={i}>
          {n.hub && <circle cx={n.x} cy={n.y} r={n.r + 6} fill="none" stroke="#1A2528" strokeWidth="1" />}
          <circle cx={n.x} cy={n.y} r={n.r}
            fill={n.red ? '#D93B2B' : (n.hub ? '#1A2528' : '#7A9BAA')} />
          {n.hub && <circle cx={n.x} cy={n.y} r={n.r - 4} fill="#fff" />}
          {n.label && (
            <text x={n.x + n.r + 6} y={n.y + 4}
              style={{ font: "400 9.5px 'JetBrains Mono', monospace", fill: '#4A6370' }}>
              {n.label}
            </text>
          )}
        </g>
      ))}
    </>
  )
}

const ExtIcon = () => (
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 3h4v4M13 3 7 9M7 4H4a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h7a1 1 0 0 0 1-1V9"/>
  </svg>
)
