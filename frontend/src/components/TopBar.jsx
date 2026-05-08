import { Search, Bell, HelpCircle, Menu } from 'lucide-react'

export default function TopBar({ breadcrumb = [], actions }) {
  return (
    <div className="h-12 border-b border-gray-100 bg-white flex items-center px-5 gap-4 shrink-0">
      <button className="text-gray-400 hover:text-gray-600 lg:hidden">
        <Menu size={18} />
      </button>

      {/* Breadcrumb */}
      <div className="flex items-center gap-1.5 text-sm text-gray-400 flex-1">
        {breadcrumb.map((crumb, i) => (
          <span key={i} className="flex items-center gap-1.5">
            {i > 0 && <span className="text-gray-200">/</span>}
            <span className={i === breadcrumb.length - 1 ? 'text-gray-700 font-medium' : ''}>
              {crumb}
            </span>
          </span>
        ))}
      </div>

      {/* Search */}
      <div className="relative hidden md:block">
        <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-300" />
        <input
          placeholder="Search terms, URIs, policies..."
          className="w-64 pl-8 pr-10 py-1.5 bg-gray-50 border border-gray-100 rounded-md text-xs text-gray-600 placeholder-gray-300 focus:outline-none focus:ring-1 focus:ring-gray-200"
        />
        <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[10px] text-gray-300 font-mono">⌘K</span>
      </div>

      {/* Right icons */}
      <div className="flex items-center gap-3">
        <button className="text-gray-300 hover:text-gray-500"><Bell size={16} /></button>
        <button className="text-gray-300 hover:text-gray-500"><HelpCircle size={16} /></button>
        <div className="w-7 h-7 rounded-full bg-gray-800 text-white text-[11px] font-medium flex items-center justify-center">
          AS
        </div>
      </div>
    </div>
  )
}
