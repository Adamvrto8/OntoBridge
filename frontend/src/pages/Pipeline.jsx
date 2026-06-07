import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'

export default function Pipeline() {
  const navigate = useNavigate()
  const [file,       setFile]       = useState(null)
  const [uploadMode, setUploadMode] = useState('single')
  const [files,      setFiles]      = useState([])
  const [sourceSystem, setSourceSystem] = useState('upload')
  const [approvedBy, setApprovedBy] = useState('')
  const [useLlmNer,  setUseLlmNer]  = useState(false)
  const [useLlmDef,  setUseLlmDef]  = useState(false)
  const [llmBackend, setLlmBackend] = useState('anthropic')
  const [llmModel,   setLlmModel]   = useState('claude-haiku-4-5-20251001')
  const [llmApiKey,  setLlmApiKey]  = useState('')
  const [result,     setResult]     = useState(null)
  const [loading,    setLoading]    = useState(false)
  const [error,      setError]      = useState(null)
  const inputRef = useRef()
  const showLlm = useLlmNer || useLlmDef

  const hasFiles = uploadMode === 'single' ? !!file : files.length > 0

  const run = async () => {
    if (!hasFiles) return
    setLoading(true); setError(null); setResult(null)
    const fd = new FormData()
    if (uploadMode === 'single') {
      fd.append('files', file)
    } else {
      for (const f of files) fd.append('files', f)
    }
    fd.append('source_system', sourceSystem)
    fd.append('approved_by', approvedBy)
    fd.append('use_llm_ner', useLlmNer)
    fd.append('use_llm_def', useLlmDef)
    fd.append('llm_backend', llmBackend)
    fd.append('llm_model', llmModel)
    if (llmApiKey.trim()) fd.append('llm_api_key', llmApiKey.trim())
    try { setResult(await api.pipeline.run(fd)) }
    catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Run Pipeline</h1>
          <div className="sub">Upload a document to extract and govern business terms.</div>
        </div>
      </div>

      <div style={{ maxWidth: 640, display: 'flex', flexDirection: 'column', gap: 'var(--gap)' }}>

        {/* Upload mode toggle */}
        <div style={{ display: 'flex', gap: 20 }}>
          <Radio label="Single file"    value="single" current={uploadMode}
            onChange={mode => { setUploadMode(mode); setFile(null); setFiles([]) }} />
          <Radio label="Multiple files" value="multi"  current={uploadMode}
            onChange={mode => { setUploadMode(mode); setFile(null); setFiles([]) }} />
        </div>

        {/* File drop zone */}
        <div
          className="card"
          onClick={() => inputRef.current?.click()}
          style={{
            padding: '32px 24px', textAlign: 'center', cursor: 'pointer',
            border: `2px dashed ${hasFiles ? 'var(--green)' : 'var(--ice)'}`,
            background: hasFiles ? 'var(--green-bg)' : 'var(--surface)',
            transition: 'border-color .15s, background .15s',
          }}
          onMouseEnter={e => { if (!hasFiles) e.currentTarget.style.borderColor = 'var(--slate-d)' }}
          onMouseLeave={e => { if (!hasFiles) e.currentTarget.style.borderColor = 'var(--ice)' }}
        >
          <UploadIcon color={hasFiles ? 'var(--green)' : 'var(--ink-3)'} />
          {hasFiles ? (
            uploadMode === 'single' ? (
              <p style={{ marginTop: 8, fontWeight: 500, color: 'var(--green)' }}>{file.name}</p>
            ) : (
              <div style={{ marginTop: 8 }}>
                <p style={{ fontWeight: 500, color: 'var(--green)' }}>
                  {files.length} file{files.length !== 1 ? 's' : ''} selected
                </p>
                <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 2 }}>
                  {files.map((f, i) => (
                    <span key={i} className="mono" style={{ color: 'var(--green)', fontSize: 11 }}>{f.name}</span>
                  ))}
                </div>
              </div>
            )
          ) : (
            <>
              <p style={{ marginTop: 8, fontWeight: 500, color: 'var(--ink)' }}>Click to upload</p>
              <p className="mono" style={{ color: 'var(--ink-3)', marginTop: 4 }}>TXT · PDF · DOCX · CSV</p>
            </>
          )}
          <input
            ref={inputRef}
            type="file"
            accept=".txt,.pdf,.docx,.csv"
            style={{ display: 'none' }}
            multiple={uploadMode === 'multi'}
            onChange={e => {
              if (uploadMode === 'single') setFile(e.target.files[0] || null)
              else setFiles(Array.from(e.target.files))
              e.target.value = ''
            }}
          />
        </div>

        {/* Fields */}
        <div className="card card-b" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <Field label="Source system" value={sourceSystem} onChange={setSourceSystem} />
          <Field label="Approved by" value={approvedBy} onChange={setApprovedBy} placeholder="optional" />
        </div>

        {/* LLM options */}
        <div className="card">
          <div className="card-h"><h3>LLM Options</h3></div>
          <div className="card-b" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'flex', gap: 24 }}>
              <Toggle label="Use LLM extractor"  value={useLlmNer} onChange={setUseLlmNer} />
              <Toggle label="Improve definitions" value={useLlmDef} onChange={setUseLlmDef} />
            </div>
            <div style={{ color: 'var(--ink-3)', fontSize: 12, lineHeight: 1.5, marginTop: 6 }}>
              When enabled, the selected LLM backend also helps the pipeline decide whether closely related extracted terms are synonyms and should be merged.
            </div>
            {showLlm && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, paddingTop: 4 }}>
                <div style={{ display: 'flex', gap: 20 }}>
                  <Radio label="Anthropic API"  value="anthropic" current={llmBackend} onChange={setLlmBackend} />
                  <Radio label="Ollama (local)" value="ollama"    current={llmBackend} onChange={setLlmBackend} />
                </div>
                {llmBackend === 'anthropic' ? (
                  <>
                    <select value={llmModel} onChange={e => setLlmModel(e.target.value)} style={inputStyle}>
                      <option value="claude-haiku-4-5-20251001">claude-haiku (fast)</option>
                      <option value="claude-sonnet-4-6">claude-sonnet (better)</option>
                      <option value="claude-opus-4-7">claude-opus (best)</option>
                    </select>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      <label style={{ font: '500 11px var(--font-sans)', color: 'var(--ink-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                        API Key <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>(leave blank to use ANTHROPIC_API_KEY env var)</span>
                      </label>
                      <input
                        type="password"
                        value={llmApiKey}
                        onChange={e => setLlmApiKey(e.target.value)}
                        placeholder="sk-ant-…"
                        style={inputStyle}
                      />
                    </div>
                  </>
                ) : (
                  <input value={llmModel} onChange={e => setLlmModel(e.target.value)}
                    placeholder="e.g. llama3.2:1b" style={inputStyle} />
                )}
              </div>
            )}
          </div>
        </div>

        <button
          className="btn primary"
          onClick={run}
          disabled={!hasFiles || loading}
          style={{ height: 36, width: '100%', justifyContent: 'center', opacity: (!hasFiles || loading) ? 0.5 : 1 }}
        >
          {loading ? 'Running…' : 'Run Pipeline'}
        </button>

        {error && (
          <div style={{ padding: '12px 16px', borderRadius: 'var(--r)', background: 'var(--red-bg)', color: 'var(--red)', fontSize: 13 }}>
            {error}
          </div>
        )}

        {result && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--gap)' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 'var(--gap)' }}>
              <ResultCard label="Published" value={result.published} color="var(--green)" bg="var(--green-bg)" />
              <ResultCard label="Skipped"   value={result.skipped}   color="var(--amber)" bg="var(--amber-bg)" />
              <ResultCard label="Failed"    value={result.failed}    color="var(--red)"   bg="var(--red-bg)" />
            </div>
            {result.skipped_details && result.skipped_details.length > 0 && (
              <div className="card">
                <div className="card-h"><h3>Skipped details</h3><span className="meta mono">{result.skipped_details.length} total</span></div>
                <table className="issues">
                  <thead><tr><th>Term</th><th>Reason</th></tr></thead>
                  <tbody>
                    {result.skipped_details.map((item, index) => (
                      <tr key={`${item.label}-${index}`}>
                        <td>
                          <div style={{ fontWeight: 500 }}>{item.label}</div>
                        </td>
                        <td style={{ color: 'var(--ink-3)' }}>{item.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {result.terms.length > 0 && (
              <div className="card">
                <div className="card-h"><h3>Extracted terms</h3><span className="meta mono">{result.terms.length} total</span></div>
                <table className="issues">
                  <thead><tr><th>Term</th><th>Status</th><th>Scheme</th></tr></thead>
                  <tbody>
                    {result.terms.map(t => (
                      <tr key={t.term_uri}
                        style={{ cursor: 'pointer' }}
                        onClick={() => navigate('/terms?uri=' + encodeURIComponent(t.term_uri))}
                      >
                        <td>
                          <div style={{ fontWeight: 500 }}>{t.preferred_label}</div>
                          <div className="mono" style={{ color: 'var(--ink-3)', marginTop: 2 }}>{t.term_uri.split('/').pop()}</div>
                        </td>
                        <td><StatusPill status={t.lifecycle_status} /></td>
                        <td>{t.scheme_label && <span className="scheme-pill">{t.scheme_label}</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  )
}

const inputStyle = {
  height: 32, padding: '0 10px', width: '100%',
  border: '1px solid var(--ice)', borderRadius: 'var(--r)',
  background: 'var(--surface)', font: '400 13px var(--font-sans)',
  color: 'var(--ink)', outline: 'none',
}

function Field({ label, value, onChange, placeholder }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <label style={{ font: '500 11px var(--font-sans)', color: 'var(--ink-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {label}
      </label>
      <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} style={inputStyle} />
    </div>
  )
}

function Toggle({ label, value, onChange }) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', userSelect: 'none' }}>
      <button type="button" onClick={() => onChange(!value)} style={{
        width: 36, height: 20, borderRadius: 10, border: 'none', padding: 0, position: 'relative',
        background: value ? 'var(--ink)' : 'var(--ice)', cursor: 'pointer', transition: 'background .15s',
      }}>
        <span style={{
          position: 'absolute', top: 2, left: value ? 18 : 2,
          width: 16, height: 16, borderRadius: '50%', background: '#fff',
          transition: 'left .15s', boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
        }} />
      </button>
      <span style={{ font: '400 13px var(--font-sans)', color: 'var(--ink-2)' }}>{label}</span>
    </label>
  )
}

function Radio({ label, value, current, onChange }) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
      <input type="radio" checked={current === value} onChange={() => onChange(value)} />
      <span style={{ font: '400 13px var(--font-sans)', color: 'var(--ink-2)' }}>{label}</span>
    </label>
  )
}

function ResultCard({ label, value, color, bg }) {
  return (
    <div className="card" style={{ padding: '16px 20px', background: bg, borderColor: color + '33', textAlign: 'center' }}>
      <div style={{ font: `400 32px var(--font-sans)`, color, letterSpacing: '-0.02em', fontFeatureSettings: '"tnum"' }}>{value}</div>
      <div style={{ font: '400 11px var(--font-sans)', color, textTransform: 'uppercase', letterSpacing: '0.08em', marginTop: 4 }}>{label}</div>
    </div>
  )
}

function StatusPill({ status }) {
  const map = { published: 'green', review: 'amber', deprecated: 'red' }
  return <span className={`pill ${map[status] || ''}`}>{status}</span>
}

const UploadIcon = ({ color }) => (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ margin: '0 auto', display: 'block' }}>
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
  </svg>
)
