import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'

const W = 860
const H = 480
const REPULSION   = 18000
const SPRING_LEN  = 180
const SPRING_K    = 0.04
const DAMPING     = 0.78
const CENTER_K    = 0.006
const ITERATIONS  = 400
const MIN_DIST    = 60

function nodeColor(node) {
  if (node.conflict)              return '#D93B2B'
  if (node.status === 'published') return '#2E7D52'
  if (node.status === 'review')    return '#B87333'
  return '#7A9BAA'
}

function initPositions(nodes) {
  return nodes.map((_, i) => {
    const angle = (2 * Math.PI * i) / nodes.length
    const r = Math.min(W, H) * 0.38
    return {
      x: W / 2 + r * Math.cos(angle) + (Math.random() - 0.5) * 40,
      y: H / 2 + r * Math.sin(angle) + (Math.random() - 0.5) * 40,
      vx: 0,
      vy: 0,
    }
  })
}

function runLayout(nodes, edges) {
  const pos = initPositions(nodes)
  const idxById = {}
  nodes.forEach((n, i) => { idxById[n.id] = i })

  for (let iter = 0; iter < ITERATIONS; iter++) {
    const fx = new Float32Array(nodes.length)
    const fy = new Float32Array(nodes.length)

    // repulsion + minimum distance enforcement
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = pos[i].x - pos[j].x || 0.1
        const dy = pos[i].y - pos[j].y || 0.1
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        const effective = Math.max(dist, MIN_DIST)
        const f = REPULSION / (effective * effective)
        fx[i] += f * dx / dist; fy[i] += f * dy / dist
        fx[j] -= f * dx / dist; fy[j] -= f * dy / dist
      }
    }

    // spring attraction along edges
    for (const e of edges) {
      const a = idxById[e.source]
      const b = idxById[e.target]
      if (a == null || b == null) continue
      const dx = pos[b].x - pos[a].x
      const dy = pos[b].y - pos[a].y
      const dist = Math.sqrt(dx * dx + dy * dy) || 1
      const f = SPRING_K * (dist - SPRING_LEN)
      fx[a] += f * dx / dist; fy[a] += f * dy / dist
      fx[b] -= f * dx / dist; fy[b] -= f * dy / dist
    }

    // center gravity
    for (let i = 0; i < nodes.length; i++) {
      fx[i] += CENTER_K * (W / 2 - pos[i].x)
      fy[i] += CENTER_K * (H / 2 - pos[i].y)
      pos[i].vx = (pos[i].vx + fx[i]) * DAMPING
      pos[i].vy = (pos[i].vy + fy[i]) * DAMPING
      pos[i].x = Math.max(30, Math.min(W - 30, pos[i].x + pos[i].vx))
      pos[i].y = Math.max(20, Math.min(H - 20, pos[i].y + pos[i].vy))
    }
  }
  return pos
}

export default function Graph() {
  const [data,    setData]    = useState(null)
  const [pos,     setPos]     = useState([])
  const [hovered, setHovered] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    api.graph.get()
      .then(d => {
        setData(d)
        if (d.nodes.length) setPos(runLayout(d.nodes, d.edges))
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const idxById = {}
  data?.nodes.forEach((n, i) => { idxById[n.id] = i })

  const handleNodeClick = (node) => {
    navigate('/terms?uri=' + encodeURIComponent(node.id))
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Knowledge Graph</h1>
          <div className="sub">Live term relationship graph — edges are resolved semantic relations.</div>
        </div>
        {data && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 12, color: 'var(--ink-3)' }}>
            <span className="mono">{data.nodes.length} terms</span>
            <span>·</span>
            <span className="mono">{data.edges.length} edges</span>
          </div>
        )}
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {loading && (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--ink-3)', fontSize: 13 }}>
            Loading graph…
          </div>
        )}
        {error && (
          <div style={{ padding: 20, color: 'var(--red)', fontSize: 13 }}>{error}</div>
        )}
        {!loading && !error && data?.nodes.length === 0 && (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--ink-3)', fontSize: 13 }}>
            No terms yet — run the pipeline to populate the graph.
          </div>
        )}
        {!loading && !error && data?.nodes.length > 0 && (
          <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', display: 'block', background: 'var(--surface)' }}>
            <defs>
              <marker id="arr" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6 Z" fill="#B0C4CC" />
              </marker>
            </defs>

            {/* edges */}
            {data.edges.map((e, i) => {
              const ai = idxById[e.source], bi = idxById[e.target]
              if (ai == null || bi == null) return null
              const a = pos[ai], b = pos[bi]
              if (!a || !b) return null
              const dx = b.x - a.x, dy = b.y - a.y
              const dist = Math.sqrt(dx * dx + dy * dy) || 1
              const r = 7
              const ex = b.x - (dx / dist) * r
              const ey = b.y - (dy / dist) * r
              return (
                <g key={i}>
                  <line x1={a.x} y1={a.y} x2={ex} y2={ey}
                    stroke="#B0C4CC" strokeWidth="1" markerEnd="url(#arr)" opacity="0.7" />
                  <text
                    x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 4}
                    style={{ font: "400 8px 'JetBrains Mono', monospace", fill: '#9AABB3', pointerEvents: 'none' }}
                    textAnchor="middle"
                  >{e.predicate}</text>
                </g>
              )
            })}

            {/* nodes */}
            {data.nodes.map((n, i) => {
              const p = pos[i]
              if (!p) return null
              const color  = nodeColor(n)
              const isHov  = hovered === n.id
              const r      = 7
              return (
                <g key={n.id} style={{ cursor: 'pointer' }}
                  onClick={() => handleNodeClick(n)}
                  onMouseEnter={() => setHovered(n.id)}
                  onMouseLeave={() => setHovered(null)}
                >
                  {isHov && <circle cx={p.x} cy={p.y} r={r + 5} fill={color} opacity="0.15" />}
                  <circle cx={p.x} cy={p.y} r={r} fill={color} />
                  <text
                    x={p.x + r + 5} y={p.y + 4}
                    style={{
                      font: `${isHov ? 500 : 400} 9.5px 'JetBrains Mono', monospace`,
                      fill: isHov ? 'var(--ink)' : '#4A6370',
                      pointerEvents: 'none',
                    }}
                  >{n.label}</text>
                  {n.scheme && (
                    <text
                      x={p.x + r + 5} y={p.y + 15}
                      style={{ font: "400 8px 'JetBrains Mono', monospace", fill: '#9AABB3', pointerEvents: 'none' }}
                    >{n.scheme}</text>
                  )}
                </g>
              )
            })}

            {/* hover tooltip */}
            {hovered && (() => {
              const idx = idxById[hovered]
              const n   = data.nodes[idx]
              const p   = pos[idx]
              if (!n || !p) return null
              const tx = p.x > W * 0.65 ? p.x - 155 : p.x + 18
              const ty = p.y > H * 0.75 ? p.y - 70  : p.y + 10
              return (
                <g>
                  <rect x={tx - 6} y={ty - 14} width={160} height={60} rx="4"
                    fill="var(--ink)" opacity="0.92" />
                  <text x={tx} y={ty} style={{ font: "500 10px 'Inter Tight', sans-serif", fill: '#fff' }}>
                    {n.label}
                  </text>
                  <text x={tx} y={ty + 14} style={{ font: "400 9px 'JetBrains Mono', monospace", fill: '#9AABB3' }}>
                    {n.status}{n.scheme ? ` · ${n.scheme}` : ''}
                  </text>
                  <text x={tx} y={ty + 27} style={{ font: "400 9px 'JetBrains Mono', monospace", fill: '#9AABB3' }}>
                    click to open term detail
                  </text>
                </g>
              )
            })()}
          </svg>
        )}

        {/* legend */}
        {!loading && !error && data?.nodes.length > 0 && (
          <div style={{ display: 'flex', gap: 20, padding: '10px 16px', borderTop: '1px solid var(--ice)', fontSize: 12, color: 'var(--ink-2)', alignItems: 'center' }}>
            {[['#D93B2B', 'Conflict'], ['#2E7D52', 'Published'], ['#B87333', 'Review'], ['#7A9BAA', 'Candidate/Draft']].map(([c, l]) => (
              <span key={l} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ width: 8, height: 8, borderRadius: 4, background: c, flexShrink: 0 }} />{l}
              </span>
            ))}
            <span style={{ marginLeft: 'auto', color: 'var(--ink-3)' }}>
              Click any node to open term detail
            </span>
          </div>
        )}
      </div>
    </>
  )
}
