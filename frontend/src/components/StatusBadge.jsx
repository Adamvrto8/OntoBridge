const COLORS = {
  candidate: 'bg-gray-100 text-gray-700',
  draft:     'bg-blue-100 text-blue-700',
  review:    'bg-amber-100 text-amber-700',
  published: 'bg-green-100 text-green-700',
  deprecated:'bg-red-100  text-red-700',
}

export default function StatusBadge({ status }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium capitalize ${COLORS[status] || 'bg-gray-100 text-gray-600'}`}>
      {status}
    </span>
  )
}
