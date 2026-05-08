export default function MetricCard({ label, value, delta, deltaUp, alert = false }) {
  const deltaClass = deltaUp === true ? ' up' : deltaUp === false ? ' down' : ''
  return (
    <div className={`metric${alert ? ' alert' : ''}`}>
      <div className="lbl">{label}</div>
      <div className="num">{value ?? '—'}</div>
      {delta && (
        <div className={`delta${deltaClass}`}>
          {deltaUp === true  && <Arrow up />}
          {deltaUp === false && <Arrow />}
          <span>{delta}</span>
        </div>
      )}
    </div>
  )
}

const Arrow = ({ up }) => (
  <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d={up ? "M4 10l4-4 4 4" : "M4 6l4 4 4-4"} />
  </svg>
)
