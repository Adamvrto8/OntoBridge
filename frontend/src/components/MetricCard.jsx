import Sparkline from './Sparkline'

export default function MetricCard({ label, value, trend, trendLabel, color = '#6366f1', negative = false }) {
  const hasTrend  = trend !== undefined
  const trendUp   = hasTrend && trend >= 0
  const trendColor = negative
    ? (trendUp ? 'text-red-500' : 'text-emerald-600')
    : (trendUp ? 'text-emerald-600' : 'text-red-500')

  return (
    <div className="bg-white border border-gray-100 rounded-xl overflow-hidden flex flex-col shadow-sm hover:shadow-md transition-shadow min-w-0">
      <div className="h-0.5 w-full" style={{ background: color }} />
      <div className="p-4 flex flex-col gap-2 flex-1">
        <p className="text-[10px] font-semibold tracking-widest text-gray-400 uppercase truncate">{label}</p>
        <div className="flex items-end justify-between gap-2">
          <div>
            <p className="text-2xl font-bold text-gray-900 leading-none tabular-nums">{value}</p>
            {hasTrend && (
              <p className={`text-xs mt-1.5 font-medium ${trendColor}`}>
                {trendUp ? '↑' : '↓'} {Math.abs(trend)}{trendLabel ? ` ${trendLabel}` : ''}
              </p>
            )}
          </div>
          <Sparkline
            value={typeof value === 'string' ? parseFloat(value) || 0 : value}
            color={color}
            negative={negative}
          />
        </div>
      </div>
    </div>
  )
}
