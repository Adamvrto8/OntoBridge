import { AreaChart, Area, ResponsiveContainer } from 'recharts'

function seed(base, n = 10) {
  const pts = []
  let v = base
  for (let i = 0; i < n; i++) {
    v = Math.max(0, v + (Math.random() - 0.48) * base * 0.12)
    pts.push({ v })
  }
  pts.push({ v: base })
  return pts
}

export default function Sparkline({ value = 100, color = '#6366f1', negative = false }) {
  const data = seed(value)
  const stroke = negative ? '#ef4444' : color
  const fill = negative ? '#fef2f2' : '#eef2ff'
  return (
    <ResponsiveContainer width={80} height={32}>
      <AreaChart data={data} margin={{ top: 2, bottom: 2, left: 0, right: 0 }}>
        <defs>
          <linearGradient id={`sg-${color.replace('#','')}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity={0.3} />
            <stop offset="100%" stopColor={stroke} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="v"
          stroke={stroke}
          strokeWidth={1.5}
          fill={`url(#sg-${color.replace('#','')})`}
          dot={false}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
