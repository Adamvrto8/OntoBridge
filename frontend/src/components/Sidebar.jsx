import { NavLink } from 'react-router-dom'
import {
  Inbox, Search, Upload, BarChart2, GitBranch,
  ScrollText, Layout, CheckSquare, FileText,
  BookOpen, Network, Layers, MapPin,
  Zap, Settings, Shield,
} from 'lucide-react'

const SECTIONS = [
  {
    label: 'WORKFLOW',
    items: [
      { to: '/',         label: 'Governance inbox', icon: Inbox,       countKey: 'Governance Inbox' },
      { to: '/reviews',  label: 'My reviews',        icon: CheckSquare, countKey: 'My Reviews', disabled: true },
      { to: '/drafts',   label: 'Drafts',             icon: FileText,    countKey: 'Drafts', disabled: true },
    ],
  },
  {
    label: 'ONTOLOGY',
    items: [
      { to: '/glossary', label: 'Glossary',       icon: BookOpen,    countKey: 'Glossary Browser' },
      { to: '/graph',    label: 'Knowledge graph', icon: Network },
      { to: '/taxonomy', label: 'Taxonomy',        icon: Layers,      disabled: true },
      { to: '/fibo',     label: 'FIBO mapping',    icon: MapPin,      disabled: true },
    ],
  },
  {
    label: 'PIPELINE',
    items: [
      { to: '/pipeline',  label: 'Harvesters',    icon: Zap },
      { to: '/stats',     label: 'Pipeline stats', icon: BarChart2 },
      { to: '/audit',     label: 'Audit log',      icon: ScrollText,  countKey: 'Audit Log' },
    ],
  },
  {
    label: 'SETTINGS',
    items: [
      { to: '/miro',      label: 'Miro board',  icon: Layout },
      { to: '/settings',  label: 'Settings',    icon: Settings, disabled: true },
    ],
  },
]

export default function Sidebar({ counts = {} }) {
  return (
    <aside className="w-52 shrink-0 bg-white border-r border-gray-100 flex flex-col min-h-screen">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-gray-100">
        <span className="text-base font-semibold tracking-tight text-gray-900">ontobridge.</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 overflow-y-auto">
        {SECTIONS.map(({ label, items }) => (
          <div key={label} className="mb-5">
            <p className="px-3 mb-1.5 text-[10px] font-semibold tracking-widest text-gray-400 uppercase">
              {label}
            </p>
            {items.map(({ to, label: itemLabel, icon: Icon, countKey, disabled }) => {
              const count = countKey ? counts[countKey] : 0
              if (disabled) {
                return (
                  <div key={to} className="flex items-center gap-2.5 px-3 py-1.5 rounded-md text-sm text-gray-300 cursor-not-allowed select-none">
                    <Icon size={14} />
                    <span className="flex-1">{itemLabel}</span>
                    {count > 0 && <Badge n={count} />}
                  </div>
                )
              }
              return (
                <NavLink
                  key={to}
                  to={to}
                  end={to === '/'}
                  className={({ isActive }) =>
                    `flex items-center gap-2.5 px-3 py-1.5 rounded-md text-sm transition-colors ${
                      isActive
                        ? 'bg-gray-100 text-gray-900 font-medium'
                        : 'text-gray-500 hover:text-gray-900 hover:bg-gray-50'
                    }`
                  }
                >
                  <Icon size={14} />
                  <span className="flex-1">{itemLabel}</span>
                  {count > 0 && <Badge n={count} />}
                </NavLink>
              )
            })}
          </div>
        ))}
      </nav>
    </aside>
  )
}

function Badge({ n }) {
  return (
    <span className="text-[11px] font-medium bg-gray-100 text-gray-500 rounded px-1.5 py-0.5 leading-none">
      {n}
    </span>
  )
}
