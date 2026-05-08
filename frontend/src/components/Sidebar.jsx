import { NavLink } from 'react-router-dom'
import {
  Inbox, BookOpen, Network, Zap,
  BarChart2, ScrollText, Layout,
} from 'lucide-react'

const SECTIONS = [
  {
    label: 'Workflow',
    items: [
      { to: '/',         label: 'Governance inbox', icon: Inbox,      countKey: 'Governance Inbox', alert: true },
    ],
  },
  {
    label: 'Ontology',
    items: [
      { to: '/glossary', label: 'Glossary',         icon: BookOpen,   countKey: 'Glossary Browser' },
      { to: '/graph',    label: 'Knowledge graph',   icon: Network },
    ],
  },
  {
    label: 'Pipeline',
    items: [
      { to: '/pipeline', label: 'Run pipeline',      icon: Zap },
      { to: '/stats',    label: 'Pipeline stats',    icon: BarChart2 },
      { to: '/audit',    label: 'Audit log',         icon: ScrollText, countKey: 'Audit Log' },
    ],
  },
  {
    label: 'Tools',
    items: [
      { to: '/miro',     label: 'Miro board',        icon: Layout },
    ],
  },
]

export default function Sidebar({ counts = {} }) {
  return (
    <aside className="w-72 shrink-0 bg-white border-r border-gray-100 flex flex-col min-h-screen">

      {/* Logo */}
      <div className="px-6 py-6 flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-gray-900 flex items-center justify-center shrink-0">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="3" fill="white" />
            <circle cx="8" cy="8" r="6" stroke="white" strokeWidth="1.5" fill="none" />
            <line x1="8" y1="2" x2="3" y2="5" stroke="white" strokeWidth="1.2" strokeLinecap="round"/>
            <line x1="8" y1="2" x2="13" y2="5" stroke="white" strokeWidth="1.2" strokeLinecap="round"/>
            <line x1="8" y1="14" x2="3" y2="11" stroke="white" strokeWidth="1.2" strokeLinecap="round"/>
            <line x1="8" y1="14" x2="13" y2="11" stroke="white" strokeWidth="1.2" strokeLinecap="round"/>
          </svg>
        </div>
        <span className="text-[16px] font-semibold tracking-tight text-gray-900">ontobridge.</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-4 pb-6 space-y-7 overflow-y-auto">
        {SECTIONS.map(({ label, items }) => (
          <div key={label}>
            <p className="px-3 mb-2 text-[10px] font-bold tracking-[0.12em] text-gray-400 uppercase">
              {label}
            </p>
            <div className="space-y-0.5">
              {items.map(({ to, label: itemLabel, icon: Icon, countKey, alert }) => {
                const count = countKey ? (counts[countKey] ?? 0) : 0
                return (
                  <NavLink
                    key={to}
                    to={to}
                    end={to === '/'}
                    className={({ isActive }) =>
                      `group flex items-center gap-3 px-3 py-2.5 rounded-xl text-[14px] font-medium transition-colors duration-150 ${
                        isActive
                          ? 'bg-gray-100 text-gray-900'
                          : 'text-gray-500 hover:bg-gray-50 hover:text-gray-800'
                      }`
                    }
                  >
                    {({ isActive }) => (
                      <>
                        <Icon
                          size={16}
                          className={`shrink-0 transition-colors ${isActive ? 'text-gray-700' : 'text-gray-400 group-hover:text-gray-600'}`}
                        />
                        <span className="flex-1 leading-none">{itemLabel}</span>
                        {count > 0 && (
                          alert
                            ? <AlertBadge n={count} />
                            : <CountBadge n={count} />
                        )}
                      </>
                    )}
                  </NavLink>
                )
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-6 py-4 border-t border-gray-100">
        <p className="text-[11px] text-gray-300 font-medium">OntoBridge · v0.1</p>
      </div>
    </aside>
  )
}

function AlertBadge({ n }) {
  return (
    <span className="min-w-[22px] h-[22px] px-1.5 rounded-full bg-red-500 text-white text-[11px] font-bold flex items-center justify-center tabular-nums leading-none">
      {n}
    </span>
  )
}

function CountBadge({ n }) {
  return (
    <span className="px-2 py-0.5 rounded-md bg-gray-100 text-gray-500 text-[12px] font-semibold tabular-nums leading-none">
      {n}
    </span>
  )
}
