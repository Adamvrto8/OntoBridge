import { NavLink } from 'react-router-dom'
import { Inbox, Search, Upload, BarChart2, GitBranch, ScrollText } from 'lucide-react'

const NAV = [
  { to: '/',          label: 'Governance Inbox', icon: Inbox },
  { to: '/glossary',  label: 'Glossary',         icon: Search },
  { to: '/pipeline',  label: 'Run Pipeline',      icon: Upload },
  { to: '/stats',     label: 'Stats',             icon: BarChart2 },
  { to: '/graph',     label: 'Knowledge Graph',   icon: GitBranch },
  { to: '/audit',     label: 'Audit Log',         icon: ScrollText },
]

export default function Sidebar({ counts = {} }) {
  return (
    <aside className="w-56 shrink-0 bg-white border-r border-gray-200 flex flex-col min-h-screen">
      <div className="px-5 py-6 border-b border-gray-100">
        <div className="text-lg font-semibold text-gray-900">OntoBridge</div>
        <div className="text-xs text-gray-400 mt-0.5">Steward Dashboard</div>
      </div>
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'bg-indigo-50 text-indigo-700 font-medium'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
              }`
            }
          >
            <Icon size={16} />
            <span className="flex-1">{label}</span>
            {counts[label] > 0 && (
              <span className="bg-indigo-600 text-white text-xs rounded-full px-1.5 py-0.5 leading-none">
                {counts[label]}
              </span>
            )}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
