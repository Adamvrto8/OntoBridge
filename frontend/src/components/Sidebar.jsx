import { NavLink, Link } from 'react-router-dom'

/* ── Icons (must be declared before NAV references them) ─────────────────── */
const ic = (d) => () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor"
       strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d={d} />
  </svg>
)

const InboxIcon  = ic("M2 9.5V12a1.5 1.5 0 0 0 1.5 1.5h9A1.5 1.5 0 0 0 14 12V9.5M2 9.5l1.4-5A1.5 1.5 0 0 1 4.85 3.5h6.3a1.5 1.5 0 0 1 1.45 1L14 9.5M2 9.5h3l1 1.5h4l1-1.5h3")
const BookIcon   = ic("M3 3h4a2 2 0 0 1 2 2v8a2 2 0 0 0-2-2H3V3zM13 3H9a2 2 0 0 0-2 2v8a2 2 0 0 1 2-2h4V3z")
const DownIcon   = ic("M8 2v9m-3-3 3 3 3-3M3 13.5h10")
const ChartIcon  = ic("M2 13.5h12M4 11V7M7 11V4M10 11V8M13 11V6")
const ListIcon   = ic("M3 4h10M3 8h10M3 12h7")
const LayoutIcon = ic("M2 3h12v4H2zM2 9h6v4H2zM10 9h4v4h-4z")

const GraphIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor"
       strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="4" cy="12" r="1.5"/><circle cx="12" cy="4" r="1.5"/>
    <circle cx="11" cy="12" r="1.5"/><circle cx="5" cy="5" r="1.5"/>
    <path d="M5.8 6 11 4.6M5 6.5l-.6 4M11.5 5.4l-.4 5M5.5 12h4"/>
  </svg>
)

/* ── Nav structure ───────────────────────────────────────────────────────── */
const NAV = [
  {
    label: 'Workflow',
    items: [
      { to: '/',         label: 'Governance inbox', countKey: 'inbox',    alert: true, icon: InboxIcon },
    ],
  },
  {
    label: 'Ontology',
    items: [
      { to: '/glossary', label: 'Glossary',                               icon: BookIcon },
      { to: '/graph',    label: 'Knowledge graph',                          icon: GraphIcon },
    ],
  },
  {
    label: 'Pipeline',
    items: [
      { to: '/pipeline', label: 'Run pipeline',                             icon: DownIcon },
      { to: '/stats',    label: 'Pipeline stats',                           icon: ChartIcon },
      { to: '/audit',    label: 'Audit log',          countKey: 'audit',   icon: ListIcon },
    ],
  },
  {
    label: 'Tools',
    items: [
      { to: '/miro',     label: 'Miro board',                               icon: LayoutIcon },
    ],
  },
]

/* ── Logo ────────────────────────────────────────────────────────────────── */
const Logo = () => (
  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true" fill="none">
      <g stroke="#7A9BAA" strokeWidth="0.9" strokeLinecap="round">
        <line x1="12" y1="12" x2="3.5"  y2="6" />
        <line x1="12" y1="12" x2="20.5" y2="6.5" />
        <line x1="12" y1="12" x2="4"    y2="19" />
        <line x1="12" y1="12" x2="20"   y2="19" />
      </g>
      <circle cx="12"  cy="12"  r="5.4" fill="none" stroke="#1A2528" strokeWidth="0.9" />
      <circle cx="12"  cy="12"  r="3.6" fill="#1A2528" />
      <circle cx="12"  cy="12"  r="1.6" fill="#FFFFFF" />
      <circle cx="3.5" cy="6"   r="1.4" fill="#1A2528" />
      <circle cx="4"   cy="19"  r="1.2" fill="#7A9BAA" />
      <circle cx="20"  cy="19"  r="1.2" fill="#7A9BAA" />
      <circle cx="20.5" cy="6.5" r="1.6" fill="#D93B2B" />
    </svg>
    <span className="word">ontobridge<span className="dot">.</span></span>
  </span>
)

/* ── Component ───────────────────────────────────────────────────────────── */
export default function Sidebar({ counts = {} }) {
  return (
    <aside className="side">
      <Link to="/" style={{ textDecoration: 'none' }}>
        <div className="brand" style={{ cursor: 'pointer' }}>
          <Logo />
        </div>
      </Link>
      <nav className="nav">
        {NAV.map(({ label, items }) => (
          <div key={label}>
            <div className="group-label">{label}</div>
            {items.map(({ to, label: lbl, countKey, alert, icon: Icon }) => {
              const count = countKey ? (counts[countKey] ?? 0) : 0
              return (
                <NavLink
                  key={to}
                  to={to}
                  end={to === '/'}
                  className={({ isActive }) => isActive ? 'active' : ''}
                >
                  <span className="ic"><Icon /></span>
                  <span className="lbl">{lbl}</span>
                  {count > 0 && (
                    <span className={`badge${alert ? ' red' : ''}`}>{count}</span>
                  )}
                </NavLink>
              )
            })}
          </div>
        ))}
      </nav>
      <div className="foot">
        <span className="pulse" />
        <span>OntoBridge · v0.1</span>
      </div>
    </aside>
  )
}
