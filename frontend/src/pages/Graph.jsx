export default function Graph() {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold text-gray-900 mb-1">Knowledge Graph</h1>
      <p className="text-sm text-gray-500 mb-6">Interactive term relationship graph — served from the Streamlit dashboard.</p>
      <div className="bg-white border border-gray-200 rounded-xl p-6 text-center text-gray-400 text-sm">
        Open the Streamlit dashboard on <code className="bg-gray-100 px-1.5 py-0.5 rounded text-xs">localhost:8501</code> to view the interactive knowledge graph.
      </div>
    </div>
  )
}
