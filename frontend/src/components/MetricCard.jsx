import Sparkline from './Sparkline'

export default function MetricCard({ label, value, trend, trendLabel, color, negative = false }) {
  const trendUp = trend >= 0
  const trendColor = negative
    ? (trendUp ? 'text-red-500' : 'text-green-500')
    : (trendUp ? 'text-green-600' : 'text-red-500')

  return (
    <div className="bg-white border border-gray-100 rounded-xl p-4 flex flex-col gap-2 min-w-0">
      <p className="text-[10px] font-semibold tracking-widest text-gray-400 uppercase truncate">{label}</p>
      <div className="flex items-end justify-between gap-2">
        <div>
          <p className="text-2xl font-semibold text-gray-900 leading-none">{value}</p>
          {trend !== undefined && (
            <p className={`text-xs mt-1 ${trendColor}`}>
              {trendUp ? '↑' : '↓'} {Math.abs(trend)} {trendLabel}
            </p>
          )}
        </div>
        <Sparkline value={typeof value === 'string' ? parseFloat(value) || 100 : value} color={color} negative={negative} />
      </div>
    </div>
  )
}
