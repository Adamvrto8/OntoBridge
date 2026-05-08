import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'

const COLORS = {
  candidate:  '#d1d5db',
  draft:      '#93c5fd',
  review:     '#6366f1',
  published:  '#111827',
  deprecated: '#fca5a5',
}

export default function LifecycleDonut({ byStatus = {}, total = 0 }) {
  const data = Object.entries(byStatus)
    .filter(([, v]) => v > 0)
    .map(([k, v]) => ({ name: k, value: v }))

  return (
    <div className="bg-white border border-gray-100 rounded-xl p-5 flex flex-col">
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-4">Lifecycle breakdown</p>
      <div className="flex items-center gap-4 flex-1">
        <div className="relative w-28 h-28 shrink-0">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={data} cx="50%" cy="50%" innerRadius={32} outerRadius={50}
                dataKey="value" stroke="none" isAnimationActive={false}>
                {data.map((entry) => (
                  <Cell key={entry.name} fill={COLORS[entry.name] || '#e5e7eb'} />
                ))}
              </Pie>
              <Tooltip
                formatter={(v, n) => [`${v} (${Math.round(v/total*100)}%)`, n]}
                contentStyle={{ fontSize: 11, border: '1px solid #e5e7eb', borderRadius: 6 }}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
            <span className="text-lg font-semibold text-gray-900">{total}</span>
            <span className="text-[10px] text-gray-400">TERMS</span>
          </div>
        </div>
        <div className="flex flex-col gap-1.5 flex-1">
          {data.map(({ name, value }) => (
            <div key={name} className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full shrink-0" style={{ background: COLORS[name] || '#e5e7eb' }} />
              <span className="text-xs text-gray-600 capitalize flex-1">{name}</span>
              <span className="text-xs font-medium text-gray-700">{value}</span>
              <span className="text-xs text-gray-400 w-9 text-right">{Math.round(value / total * 100)}%</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
