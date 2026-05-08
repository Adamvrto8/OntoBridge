import { useRef, useState } from 'react'
import { Upload, CheckCircle } from 'lucide-react'
import { api } from '../api/client'
import StatusBadge from '../components/StatusBadge'

export default function Pipeline() {
  const [file, setFile] = useState(null)
  const [sourceSystem, setSourceSystem] = useState('upload')
  const [approvedBy, setApprovedBy] = useState('')
  const [useLlmNer, setUseLlmNer] = useState(false)
  const [useLlmDef, setUseLlmDef] = useState(false)
  const [llmBackend, setLlmBackend] = useState('anthropic')
  const [llmModel, setLlmModel] = useState('claude-haiku-4-5-20251001')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const inputRef = useRef()

  const showLlm = useLlmNer || useLlmDef

  const run = async () => {
    if (!file) return
    setLoading(true); setError(null); setResult(null)
    const fd = new FormData()
    fd.append('file', file)
    fd.append('source_system', sourceSystem)
    fd.append('approved_by', approvedBy)
    fd.append('use_llm_ner', useLlmNer)
    fd.append('use_llm_def', useLlmDef)
    fd.append('llm_backend', llmBackend)
    fd.append('llm_model', llmModel)
    try {
      const res = await api.pipeline.run(fd)
      setResult(res)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-8 max-w-2xl">
      <h1 className="text-2xl font-semibold text-gray-900 mb-1">Run Pipeline</h1>
      <p className="text-sm text-gray-500 mb-6">Upload a document to extract and govern business terms.</p>

      {/* File drop */}
      <div
        onClick={() => inputRef.current?.click()}
        className="border-2 border-dashed border-gray-200 rounded-xl p-8 text-center cursor-pointer hover:border-indigo-300 hover:bg-indigo-50/30 transition-colors mb-5"
      >
        <Upload size={24} className="mx-auto mb-2 text-gray-400" />
        {file ? (
          <p className="text-sm font-medium text-indigo-600">{file.name}</p>
        ) : (
          <>
            <p className="text-sm text-gray-600 font-medium">Click to upload</p>
            <p className="text-xs text-gray-400 mt-1">TXT, PDF, DOCX, CSV</p>
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          accept=".txt,.pdf,.docx,.csv"
          className="hidden"
          onChange={e => setFile(e.target.files[0])}
        />
      </div>

      {/* Fields */}
      <div className="grid grid-cols-2 gap-4 mb-5">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Source system</label>
          <input value={sourceSystem} onChange={e => setSourceSystem(e.target.value)}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300" />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Approved by (optional)</label>
          <input value={approvedBy} onChange={e => setApprovedBy(e.target.value)}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300" />
        </div>
      </div>

      {/* LLM toggles */}
      <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 mb-5 space-y-3">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">LLM Options</p>
        <div className="flex gap-6">
          <Toggle label="Use LLM extractor" value={useLlmNer} onChange={setUseLlmNer} />
          <Toggle label="Improve definitions" value={useLlmDef} onChange={setUseLlmDef} />
        </div>
        {showLlm && (
          <div className="space-y-3 pt-1">
            <div className="flex gap-4">
              <Radio label="Anthropic API" value="anthropic" current={llmBackend} onChange={setLlmBackend} />
              <Radio label="Ollama (local)" value="ollama" current={llmBackend} onChange={setLlmBackend} />
            </div>
            {llmBackend === 'anthropic' ? (
              <select value={llmModel} onChange={e => setLlmModel(e.target.value)}
                className="border border-gray-200 rounded-lg text-sm px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-300">
                <option value="claude-haiku-4-5-20251001">claude-haiku (fast)</option>
                <option value="claude-sonnet-4-6">claude-sonnet (better)</option>
                <option value="claude-opus-4-7">claude-opus (best)</option>
              </select>
            ) : (
              <input value={llmModel} onChange={e => setLlmModel(e.target.value)}
                placeholder="e.g. llama3.2:1b"
                className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300" />
            )}
          </div>
        )}
      </div>

      <button
        onClick={run}
        disabled={!file || loading}
        className="w-full py-2.5 bg-indigo-600 text-white rounded-lg font-medium text-sm hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        {loading ? 'Running...' : 'Run Pipeline'}
      </button>

      {error && <p className="mt-4 text-sm text-red-600 bg-red-50 rounded-lg px-4 py-3">{error}</p>}

      {result && (
        <div className="mt-6">
          <div className="grid grid-cols-3 gap-3 mb-5">
            <Metric label="Published" value={result.published} color="text-green-600" />
            <Metric label="Skipped" value={result.skipped} color="text-amber-600" />
            <Metric label="Failed" value={result.failed} color="text-red-600" />
          </div>
          {result.terms.length > 0 && (
            <div className="bg-white border border-gray-200 rounded-xl divide-y divide-gray-100">
              {result.terms.map(t => (
                <div key={t.term_uri} className="px-4 py-3 flex items-center gap-3">
                  <CheckCircle size={15} className="text-green-500 shrink-0" />
                  <span className="text-sm font-medium text-gray-800">{t.preferred_label}</span>
                  <StatusBadge status={t.lifecycle_status} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Toggle({ label, value, onChange }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer select-none">
      <button
        type="button"
        onClick={() => onChange(!value)}
        className={`w-10 h-5 rounded-full transition-colors relative ${value ? 'bg-indigo-600' : 'bg-gray-300'}`}
      >
        <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${value ? 'translate-x-5' : ''}`} />
      </button>
      <span className="text-sm text-gray-700">{label}</span>
    </label>
  )
}

function Radio({ label, value, current, onChange }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer">
      <input type="radio" checked={current === value} onChange={() => onChange(value)} className="accent-indigo-600" />
      <span className="text-sm text-gray-700">{label}</span>
    </label>
  )
}

function Metric({ label, value, color }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 text-center">
      <div className={`text-2xl font-semibold ${color}`}>{value}</div>
      <div className="text-xs text-gray-500 mt-0.5">{label}</div>
    </div>
  )
}
