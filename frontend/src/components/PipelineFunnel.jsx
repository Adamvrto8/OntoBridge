const STAGES = [
  { label: 'Harvest',    sub: 'policies + catalogs', factor: 1.00 },
  { label: 'Mapping',    sub: 'fibo + dedupe',        factor: 0.92 },
  { label: 'Taxonomy',   sub: 'skos placement',       factor: 0.84, warn: true },
  { label: 'Relations',  sub: 'verb resolution',      factor: 0.79 },
  { label: 'Governance', sub: 'rule check',           factor: 0.75, warn: true },
  { label: 'Writer',     sub: 'turtle published',     factor: null },
]

export default function PipelineFunnel({ total = 0, published = 0, lastRun = null }) {
  const ratio = total > 0 ? published / total : 0
  const counts = STAGES.map((s, i) =>
    s.factor === null ? published : Math.round(total * s.factor)
  )

  return (
    <div className="card" style={{ marginBottom: 'var(--gap)' }}>
      <div className="card-h">
        <h3>Pipeline · {lastRun ? `last run ${lastRun}` : 'no recent run'}</h3>
        <span className="meta mono">{total} → {published} published</span>
      </div>
      <div style={{ padding: '12px' }}>
        <div className="pipe">
          {STAGES.map((s, i) => (
            <div key={s.label} className={`step${s.warn ? ' warn' : ''}`}>
              <div className="nm"><span className="dot" />{s.label}</div>
              <div className="v">{counts[i]}</div>
              <div className="sub">{s.sub}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
