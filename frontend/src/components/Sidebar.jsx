import { NavLink } from 'react-router-dom'
import {
  Inbox, BarChart2, ScrollText, Layout,
  CheckSquare, FileText, BookOpen, Network,
  Layers, MapPin, Zap, Settings, Shield,
} from 'lucide-react'

const SECTIONS = [
  {
    label: 'Workflow',
    items: [
      { to: '/',        label: 'Governance inbox', icon: Inbox,       countKey: 'Governance Inbox', accent: true },
      { to: '/reviews', label: 'My reviews',        icon: CheckSquare, countKey: 'My Reviews',       disabled: true },
      { to: '/drafts',  label: 'Drafts',             icon: FileText,    countKey: 'Drafts',           disabled: true },
    ],
  },
  {
    label: 'Ontology',
    items: [
      { to: '/glossary', label: 'Glossary',        icon: BookOpen, countKey: 'Glossary Browser' },
      { to: '/graph',    label: 'Knowledge graph',  icon: Network },
      { to: '/taxonomy', label: 'Taxonomy',         icon: Layers,   disabled: true },
      { to: '/fibo',     label: 'FIBO mapping',     icon: MapPin,   disabled: true },
    ],
  },
  {
    label: 'Pipeline',
    items: [
      { to: '/pipeline', label: 'Harvesters',    icon: Zap },
      { to: '/stats',    label: 'Pipeline stats', icon: BarChart2 },
      { to: '/audit',    label: 'Audit log',      icon: ScrollText, countKey: 'Audit Log' },
    ],
  },
  {
    label: 'Settings',
    items: [
      { to: '/miro',     label: 'Miro board', icon: Layout },
      { to: '/policies', label: 'Policies',   icon: Shield,   disabled: true },
      { to: '/settings', label: 'Settings',   icon: Settings, disabled: true },
    ],
  },
]

export default function Sidebar({ counts = {} }) {
  return (
    <aside className="w-64 shrink-0 bg-white border-r border-gray-100 flex flex-col min-h-screen">
      {/* Logo */}
      <div className="px-5 py-[18px] border-b border-gray-100 flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-full bg-gray-900 flex items-center justify-center shrink-0">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <circle cx="7" cy="7" r="3" fill="white" />
            <circle cx="7" cy="7" r="5.5" stroke="white" strokeWidth="1.5" fill="none" />
            <line x1="7" y1="1" x2="2.5" y2="3.5" stroke="white" strokeWidth="1" />
            <line x1="7" y1="1" x2="11.5" y2="3.5" stroke="white" strokeWidth="1" />
            <line x1="7" y1="13" x2="2.5" y2="10.5" stroke="white" strokeWidth="1" />
            <line x1="7" y1="13" x2="11.5" y2="10.5" stroke="white" strokeWidth="1" />
          </svg>
        </div>
        <span className="text-[15px] font-semibold tracking-tight text-gray-900">ontobridge.</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-5 overflow-y-auto space-y-6">
        {SECTIONS.map(({ label, items }) => (
          <div key={label}>
            <p className="px-3 mb-1 text-[10px] font-semibold tracking-widest text-gray-400 uppercase">
              {label}
            </p>
            <div className="space-y-0.5">
              {items.map(({ to, label: itemLabel, icon: Icon, countKey, disabled, accent }) => {
                const count = countKey ? (counts[countKey] ?? 0) : 0

                if (disabled) {
                  return (
                    <div
                      key={to}
                      className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-300 cursor-not-allowed select-none"
                    >
                      <Icon size={15} className="shrink-0" />
                      <span className="flex-1 leading-none">{itemLabel}</span>
                      {count > 0 && <CountBadge n={count} />}
                    </div>
                  )
                }

                return (
                  <NavLink
                    key={to}
                    to={to}
                    end={to === '/'}
                    className={({ isActive }) =>
                      `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all ${
                        isActive
                          ? 'bg-gray-900 text-white font-medium shadow-sm'
                          : 'text-gray-500 hover:text-gray-900 hover:bg-gray-50'
                      }`
                    }
                  >
                    {({ isActive }) => (
                      <>
                        <Icon size={15} className="shrink-0" />
                        <span className="flex-1 leading-none">{itemLabel}</span>
                        {count > 0 && <CountBadge n={count} active={isActive} accent={accent} />}
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
      <div className="px-5 py-4 border-t border-gray-100">
        <p className="text-[11px] text-gray-300">OntoBridge · v0.1</p>
      </div>
    </aside>
  )
}

function CountBadge({ n, active = false, accent = false }) {
  if (active) {
    return (
      <span className="text-[11px] font-semibold bg-white/20 text-white rounded-md px-1.5 py-0.5 leading-none tabular-nums">
        {n}
      </span>
    )
  }
  if (accent && n > 0) {
    return (
      <span className="text-[11px] font-semibold bg-red-50 text-red-600 rounded-md px-1.5 py-0.5 leading-none tabular-nums">
        {n}
      </span>
    )
  }
  return (
    <span className="text-[11px] font-medium bg-gray-100 text-gray-500 rounded-md px-1.5 py-0.5 leading-none tabular-nums">
      {n}
    </span>
  )
}
