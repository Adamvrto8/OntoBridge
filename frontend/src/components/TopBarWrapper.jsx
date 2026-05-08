import { useLocation } from 'react-router-dom'

const CRUMBS = {
  '/':         ['Workflow', 'Governance inbox'],
  '/glossary': ['Ontology', 'Glossary'],
  '/graph':    ['Ontology', 'Knowledge graph'],
  '/pipeline': ['Pipeline', 'Run pipeline'],
  '/stats':    ['Pipeline', 'Pipeline stats'],
  '/audit':    ['Pipeline', 'Audit log'],
  '/miro':     ['Tools', 'Miro board'],
  '/terms':    ['Ontology', 'Term detail'],
}

export default function TopBarWrapper() {
  const { pathname } = useLocation()
  const key = Object.keys(CRUMBS).find(k => pathname === k || (k !== '/' && pathname.startsWith(k))) || '/'
  const [section, page] = CRUMBS[key] || ['', pathname]

  return (
    <header className="topbar">
      <div className="crumbs">
        <span>{section}</span>
        <span className="sep">/</span>
        <span className="here">{page}</span>
      </div>
      <div className="spacer" />
      <div className="search">
        <SearchIcon />
        <input placeholder="Search terms, URIs, policies…" readOnly />
        <span className="kbd">⌘K</span>
      </div>
      <button className="icon-btn" title="Notifications">
        <BellIcon />
        <span className="alert-dot" />
      </button>
      <button className="icon-btn" title="Help">
        <span style={{ font: "500 12px 'JetBrains Mono', monospace", color: 'var(--ink-2)' }}>?</span>
      </button>
      <div className="avatar" title="Current user">AS</div>
    </header>
  )
}

const SearchIcon = () => (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="7" cy="7" r="4.5"/><path d="m10.5 10.5 3 3"/>
  </svg>
)
const BellIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 11V7a4 4 0 0 1 8 0v4l1.5 1.5h-11L4 11zM6.5 13a1.5 1.5 0 0 0 3 0"/>
  </svg>
)
