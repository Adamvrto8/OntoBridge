import { useEffect, useState, useRef } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { api } from '../api/client'

const TRANSITIONS = {
  candidate:  ['draft', 'review'],
  draft:      ['review', 'candidate'],
  review:     ['published', 'draft', 'candidate'],
  published:  ['deprecated', 'review'],
  deprecated: [],
}

const STATUS_PILL = {
  candidate:  '',
  draft:      '',
  review:     'amber',
  published:  'green',
  deprecated: 'red',
}

const lcOrder = ['candidate', 'draft', 'review', 'published']

export default function TermDetail() {
  const [searchParams] = useSearchParams()
  const uri = searchParams.get('uri')
  const navigate = useNavigate()
  const [term,       setTerm]       = useState(null)
  const [error,      setError]      = useState(null)
  const [loading,    setLoading]    = useState(true)
  const [actor,      setActor]      = useState('')

  // Definition editing
  const [editingDef, setEditingDef] = useState(false)
  const [defDraft,   setDefDraft]   = useState('')
  const [defSaving,  setDefSaving]  = useState(false)
  const defRef = useRef(null)

  // Alt labels editing
  const [altDraft,    setAltDraft]    = useState([])
  const [altInput,    setAltInput]    = useState('')
  const [editingAlts, setEditingAlts] = useState(false)
  const [altSaving,   setAltSaving]   = useState(false)

  // Relations editing
  const [editingRels,  setEditingRels]  = useState(false)
  const [relsDeleted,  setRelsDeleted]  = useState(new Set())
  const [relsToAdd,    setRelsToAdd]    = useState([])
  const [relVerb,      setRelVerb]      = useState('')
  const [relObj,       setRelObj]       = useState('')
  const [knownVerbs,   setKnownVerbs]   = useState([])
  const [relsSaving,   setRelsSaving]   = useState(false)

  // Taxonomy editing
  const [editingTax,   setEditingTax]   = useState(false)
  const [taxConcepts,  setTaxConcepts]  = useState([])
  const [taxSelected,  setTaxSelected]  = useState(null)  // { uri, pref_label, scheme_uri, scheme_label }
  const [taxSaving,    setTaxSaving]    = useState(false)
  const [taxSearch,    setTaxSearch]    = useState('')

  const load = () => {
    if (!uri) { setLoading(false); return }
    setLoading(true); setError(null)
    api.terms.get(uri)
      .then(setTerm)
      .catch(e => setError(e.message || 'Failed to load term'))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [uri])

  const transition = async (newStatus) => {
    try {
      await api.terms.transition(uri, { new_status: newStatus, actor: actor || 'steward' })
      load()
    } catch (e) { alert(e.message) }
  }

  const startEditDef = () => {
    setDefDraft(term.definition || '')
    setEditingDef(true)
    setTimeout(() => defRef.current?.focus(), 0)
  }

  const saveDef = async () => {
    if (defSaving) return
    setDefSaving(true)
    try {
      const updated = await api.terms.edit(uri, { definition: defDraft, actor: actor || 'steward' })
      setTerm(updated)
      setEditingDef(false)
    } catch (e) { alert(e.message) }
    finally { setDefSaving(false) }
  }

  const cancelDef = () => { setEditingDef(false); setDefDraft('') }

  const startEditAlts = () => {
    setAltDraft([...(term.alt_labels || [])])
    setAltInput('')
    setEditingAlts(true)
  }

  const addAlt = () => {
    const val = altInput.trim()
    if (!val || altDraft.includes(val)) return
    setAltDraft(prev => [...prev, val])
    setAltInput('')
  }

  const removeAlt = (label) => setAltDraft(prev => prev.filter(l => l !== label))

  const saveAlts = async () => {
    if (altSaving) return
    setAltSaving(true)
    try {
      const updated = await api.terms.edit(uri, { alt_labels: altDraft, actor: actor || 'steward' })
      setTerm(updated)
      setEditingAlts(false)
    } catch (e) { alert(e.message) }
    finally { setAltSaving(false) }
  }

  const cancelAlts = () => { setEditingAlts(false); setAltDraft([]); setAltInput('') }

  const startEditTax = async () => {
    if (taxConcepts.length === 0) {
      const list = await api.stats.concepts().catch(() => [])
      setTaxConcepts(list)
    }
    setTaxSelected(null)
    setTaxSearch('')
    setEditingTax(true)
  }

  const saveTax = async () => {
    if (!taxSelected || taxSaving) return
    setTaxSaving(true)
    try {
      const updated = await api.terms.edit(uri, {
        broader_concept_uri: taxSelected.uri,
        scheme_uri: taxSelected.scheme_uri,
        actor: actor || 'steward',
      })
      setTerm(updated)
      setEditingTax(false)
    } catch (e) { alert(e.message) }
    finally { setTaxSaving(false) }
  }

  const cancelTax = () => { setEditingTax(false); setTaxSelected(null); setTaxSearch('') }

  const startEditRels = async () => {
    if (knownVerbs.length === 0) {
      const verbs = await api.stats.verbs().catch(() => [])
      setKnownVerbs(verbs)
    }
    setRelsDeleted(new Set())
    setRelsToAdd([])
    setRelVerb('')
    setRelObj('')
    setEditingRels(true)
  }

  const toggleDeleteRel = (idx) =>
    setRelsDeleted(prev => {
      const next = new Set(prev)
      next.has(idx) ? next.delete(idx) : next.add(idx)
      return next
    })

  const addPendingRel = () => {
    if (!relVerb.trim() || !relObj.trim()) return
    setRelsToAdd(prev => [...prev, { verb: relVerb.trim(), object_label: relObj.trim() }])
    setRelVerb('')
    setRelObj('')
  }

  const removePendingRel = (i) => setRelsToAdd(prev => prev.filter((_, idx) => idx !== i))

  const saveRels = async () => {
    if (relsSaving) return
    setRelsSaving(true)
    try {
      const updated = await api.terms.edit(uri, {
        relations_delete: relsDeleted.size > 0 ? [...relsDeleted] : undefined,
        relations_add: relsToAdd.length > 0 ? relsToAdd : undefined,
        actor: actor || 'steward',
      })
      setTerm(updated)
      setEditingRels(false)
    } catch (e) { alert(e.message) }
    finally { setRelsSaving(false) }
  }

  const cancelRels = () => { setEditingRels(false); setRelsDeleted(new Set()); setRelsToAdd([]) }

  if (!uri)    return <p style={{ color: 'var(--ink-3)', fontSize: 13 }}>No term URI provided.</p>
  if (loading) return <p style={{ color: 'var(--ink-3)', fontSize: 13 }}>Loading…</p>
  if (error)   return (
    <div style={{ padding: '16px', background: 'var(--red-bg)', borderRadius: 'var(--r)', color: 'var(--red)', fontSize: 13, maxWidth: 500 }}>
      <strong>Could not load term</strong><br />{error}<br />
      <span style={{ color: 'var(--ink-3)', fontSize: 11, marginTop: 4, display: 'block' }}>URI: {uri}</span>
    </div>
  )
  if (!term)   return <p style={{ color: 'var(--ink-3)', fontSize: 13 }}>Term not found.</p>

  const nextStatuses = TRANSITIONS[term.lifecycle_status] || []
  const lcIdx = lcOrder.indexOf(term.lifecycle_status)

  return (
    <>
      <div className="page-head">
        <div>
          <button
            className="btn ghost"
            onClick={() => navigate(-1)}
            style={{ marginBottom: 8, paddingLeft: 0 }}
          >
            ← Back
          </button>
          <h1>{term.preferred_label}</h1>
          {term.scheme_label && (
            <div className="sub" style={{ marginTop: 4 }}>
              <span className="scheme-pill">{term.scheme_label}</span>
            </div>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span className="lifecycle">
            {lcOrder.map((s, i) => (
              <span key={s} className={`b${i <= lcIdx ? ' on' : ''}`} title={s} />
            ))}
            <span style={{ marginLeft: 6 }}>{term.lifecycle_status}</span>
          </span>
          <span className={`pill ${STATUS_PILL[term.lifecycle_status] || ''}`}>
            {term.lifecycle_status}
          </span>
        </div>
      </div>

      <div style={{ maxWidth: 800, display: 'flex', flexDirection: 'column', gap: 'var(--gap)' }}>

        {/* Main card */}
        <div className="card">
          <div className="card-h">
            <h3>Definition</h3>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span className="meta mono">{term.term_uri.split('/').pop()}</span>
              {!editingDef && (
                <button className="btn ghost" style={{ height: 26, padding: '0 10px', fontSize: 12 }} onClick={startEditDef}>
                  Edit
                </button>
              )}
            </div>
          </div>
          <div className="card-b">
            {editingDef ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <textarea
                  ref={defRef}
                  value={defDraft}
                  onChange={e => setDefDraft(e.target.value)}
                  rows={5}
                  style={{
                    width: '100%', padding: '10px 12px', fontSize: 14, lineHeight: 1.6,
                    border: '1.5px solid var(--slate-d)', borderRadius: 'var(--r)',
                    background: 'var(--surface)', color: 'var(--ink)',
                    font: '400 14px var(--font-sans)', resize: 'vertical', outline: 'none',
                    boxSizing: 'border-box',
                  }}
                />
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn primary" style={{ height: 30 }} onClick={saveDef} disabled={defSaving}>
                    {defSaving ? 'Saving…' : 'Save'}
                  </button>
                  <button className="btn ghost" style={{ height: 30 }} onClick={cancelDef}>
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <p style={{ color: 'var(--ink)', lineHeight: 1.6, fontSize: 14 }}>
                {term.definition || <span style={{ color: 'var(--ink-3)', fontStyle: 'italic' }}>No definition — click Edit to add one.</span>}
              </p>
            )}

            <div style={{ marginTop: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <div style={{ font: '500 10.5px var(--font-sans)', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-3)' }}>
                  Also known as
                </div>
                {!editingAlts && (
                  <button className="btn ghost" style={{ height: 22, padding: '0 8px', fontSize: 11 }} onClick={startEditAlts}>
                    Edit
                  </button>
                )}
              </div>

              {editingAlts ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {altDraft.map(l => (
                      <span key={l} style={{
                        display: 'inline-flex', alignItems: 'center', gap: 5,
                        background: 'var(--ice)', borderRadius: 'var(--r)',
                        padding: '3px 8px', fontSize: 12, color: 'var(--ink)',
                      }}>
                        {l}
                        <button onClick={() => removeAlt(l)} style={{
                          background: 'none', border: 'none', cursor: 'pointer',
                          color: 'var(--ink-3)', fontSize: 13, lineHeight: 1, padding: 0,
                        }}>×</button>
                      </span>
                    ))}
                    {altDraft.length === 0 && (
                      <span style={{ color: 'var(--ink-3)', fontSize: 12, fontStyle: 'italic' }}>No alt labels yet</span>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <input
                      value={altInput}
                      onChange={e => setAltInput(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addAlt())}
                      placeholder="Add label… press Enter"
                      style={{
                        flex: 1, height: 30, padding: '0 10px',
                        border: '1px solid var(--ice)', borderRadius: 'var(--r)',
                        background: 'var(--surface)', font: '400 13px var(--font-sans)',
                        color: 'var(--ink)', outline: 'none',
                      }}
                    />
                    <button className="btn ghost" style={{ height: 30 }} onClick={addAlt}>Add</button>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn primary" style={{ height: 30 }} onClick={saveAlts} disabled={altSaving}>
                      {altSaving ? 'Saving…' : 'Save'}
                    </button>
                    <button className="btn ghost" style={{ height: 30 }} onClick={cancelAlts}>Cancel</button>
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {(term.alt_labels || []).length > 0
                    ? term.alt_labels.map(l => <span key={l} className="pill">{l}</span>)
                    : <span style={{ color: 'var(--ink-3)', fontSize: 12, fontStyle: 'italic' }}>None — click Edit to add</span>
                  }
                </div>
              )}
            </div>

            {term.business_rules?.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <div style={{ font: '500 10.5px var(--font-sans)', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-3)', marginBottom: 8 }}>
                  Business rules
                </div>
                {term.business_rules.map((r, i) => (
                  <div key={i} style={{
                    display: 'flex', gap: 10, padding: '6px 0',
                    borderBottom: i < term.business_rules.length - 1 ? '1px solid var(--ice)' : 0,
                    fontSize: 13, color: 'var(--ink-2)',
                  }}>
                    <span style={{ color: 'var(--slate)', flexShrink: 0 }}>·</span> {r}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Taxonomy */}
        <div className="card">
          <div className="card-h">
            <h3>Taxonomy</h3>
            {!editingTax && (
              <button className="btn ghost" style={{ height: 26, padding: '0 10px', fontSize: 12 }} onClick={startEditTax}>
                Override
              </button>
            )}
          </div>
          {editingTax ? (
            <div className="card-b" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>
                Select a concept from the ontology to use as the broader (parent) concept.
              </div>
              <input
                value={taxSearch}
                onChange={e => setTaxSearch(e.target.value)}
                placeholder="Search concepts…"
                style={{
                  height: 30, padding: '0 10px', border: '1px solid var(--ice)',
                  borderRadius: 'var(--r)', background: 'var(--surface)',
                  font: '400 13px var(--font-sans)', color: 'var(--ink)', outline: 'none',
                }}
              />
              <div style={{ maxHeight: 220, overflowY: 'auto', border: '1px solid var(--ice)', borderRadius: 'var(--r)' }}>
                {taxConcepts
                  .filter(c => !taxSearch || c.pref_label.toLowerCase().includes(taxSearch.toLowerCase()) || (c.scheme_label || '').toLowerCase().includes(taxSearch.toLowerCase()))
                  .map(c => (
                    <div
                      key={c.uri}
                      onClick={() => setTaxSelected(c)}
                      style={{
                        padding: '8px 12px', cursor: 'pointer', fontSize: 13,
                        display: 'flex', alignItems: 'center', gap: 10,
                        background: taxSelected?.uri === c.uri ? 'var(--ice)' : 'transparent',
                        borderBottom: '1px solid var(--ice)',
                      }}
                    >
                      <span style={{ flex: 1, fontWeight: taxSelected?.uri === c.uri ? 500 : 400 }}>{c.pref_label}</span>
                      {c.scheme_label && <span className="scheme-pill" style={{ fontSize: 10 }}>{c.scheme_label}</span>}
                    </div>
                  ))}
              </div>
              {taxSelected && (
                <div style={{ fontSize: 12, color: 'var(--ink-2)', padding: '6px 10px', background: 'var(--ice)', borderRadius: 'var(--r)' }}>
                  Selected: <strong>{taxSelected.pref_label}</strong> in <strong>{taxSelected.scheme_label || '—'}</strong>
                </div>
              )}
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn primary" style={{ height: 30 }} onClick={saveTax} disabled={!taxSelected || taxSaving}>
                  {taxSaving ? 'Saving…' : 'Save'}
                </button>
                <button className="btn ghost" style={{ height: 30 }} onClick={cancelTax}>Cancel</button>
              </div>
            </div>
          ) : (
            <div className="card-b" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {/* Breadcrumb path */}
              <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 4, fontSize: 13 }}>
                {term.scheme_label && (
                  <span className="scheme-pill">{term.scheme_label}</span>
                )}
                {(term.ancestor_path || []).map((label, i) => (
                  <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <span style={{ color: 'var(--ink-3)' }}>›</span>
                    <span style={{ color: 'var(--ink-2)' }}>{label}</span>
                  </span>
                ))}
                <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <span style={{ color: 'var(--ink-3)' }}>›</span>
                  <span style={{ fontWeight: 600, color: 'var(--ink)' }}>{term.preferred_label}</span>
                </span>
              </div>
              {/* Grid detail */}
              <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr', gap: '6px 16px', fontSize: 13, color: 'var(--ink-3)', borderTop: '1px solid var(--ice)', paddingTop: 10 }}>
                <span>Broader concept</span>
                <span style={{ color: 'var(--ink-2)' }}>{term.broader_label || <span style={{ fontStyle: 'italic' }}>Unresolved — click Override</span>}</span>
                <span>Scheme</span>
                <span>{term.scheme_label ? <span className="scheme-pill">{term.scheme_label}</span> : <span style={{ fontStyle: 'italic' }}>—</span>}</span>
              </div>
            </div>
          )}
        </div>

        {/* Semantic relations */}
        <div className="card">
          <div className="card-h">
            <h3>Semantic relations</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span className="meta mono">{(term.relations || []).length}</span>
              {!editingRels && (
                <button className="btn ghost" style={{ height: 26, padding: '0 10px', fontSize: 12 }} onClick={startEditRels}>
                  Edit
                </button>
              )}
            </div>
          </div>

          {editingRels ? (
            <div style={{ padding: '8px 0' }}>
              {/* Existing relations — click to mark for deletion */}
              {(term.relations || []).map((r, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px',
                  borderBottom: '1px solid var(--ice)', fontSize: 13,
                  background: relsDeleted.has(i) ? '#FFF0EE' : 'transparent',
                  opacity: relsDeleted.has(i) ? 0.5 : 1,
                  transition: 'all 0.15s',
                }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: relsDeleted.has(i) ? 'var(--red)' : 'var(--green)', flexShrink: 0 }} />
                  <span className="mono" style={{ color: 'var(--slate-d)', flex: '0 0 auto' }}>{r.predicate}</span>
                  <span style={{ color: 'var(--ink-3)' }}>→</span>
                  <span style={{ color: 'var(--ink)', fontWeight: 500, flex: 1 }}>{r.object_label}</span>
                  <button
                    onClick={() => toggleDeleteRel(i)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 16, color: relsDeleted.has(i) ? 'var(--green)' : 'var(--red)', padding: '0 4px' }}
                    title={relsDeleted.has(i) ? 'Undo remove' : 'Remove'}
                  >
                    {relsDeleted.has(i) ? '↩' : '×'}
                  </button>
                </div>
              ))}

              {/* Pending additions */}
              {relsToAdd.map((r, i) => (
                <div key={`add-${i}`} style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px',
                  borderBottom: '1px solid var(--ice)', fontSize: 13, background: '#F0FFF4',
                }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--green)', flexShrink: 0 }} />
                  <span className="mono" style={{ color: 'var(--slate-d)', flex: '0 0 auto' }}>{r.verb}</span>
                  <span style={{ color: 'var(--ink-3)' }}>→</span>
                  <span style={{ color: 'var(--ink)', fontWeight: 500, flex: 1 }}>{r.object_label}</span>
                  <span style={{ fontSize: 10, color: 'var(--green)', marginRight: 4 }}>NEW</span>
                  <button onClick={() => removePendingRel(i)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 16, color: 'var(--red)', padding: '0 4px' }}>×</button>
                </div>
              ))}

              {/* Add form */}
              <div style={{ padding: '12px 16px', borderTop: '1px solid var(--ice)', display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <input
                  list="verb-list"
                  value={relVerb}
                  onChange={e => setRelVerb(e.target.value)}
                  placeholder="Verb (e.g. governs)"
                  style={{ height: 30, padding: '0 10px', width: 160, border: '1px solid var(--ice)', borderRadius: 'var(--r)', background: 'var(--surface)', font: '400 13px var(--font-sans)', color: 'var(--ink)', outline: 'none' }}
                />
                <datalist id="verb-list">
                  {knownVerbs.map(v => <option key={v} value={v} />)}
                </datalist>
                <span style={{ color: 'var(--ink-3)', fontSize: 13 }}>→</span>
                <input
                  value={relObj}
                  onChange={e => setRelObj(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addPendingRel())}
                  placeholder="Object (e.g. credit policy)"
                  style={{ height: 30, padding: '0 10px', flex: 1, minWidth: 160, border: '1px solid var(--ice)', borderRadius: 'var(--r)', background: 'var(--surface)', font: '400 13px var(--font-sans)', color: 'var(--ink)', outline: 'none' }}
                />
                <button className="btn ghost" style={{ height: 30 }} onClick={addPendingRel}>Add</button>
              </div>

              <div style={{ padding: '8px 16px', display: 'flex', gap: 8 }}>
                <button className="btn primary" style={{ height: 30 }} onClick={saveRels} disabled={relsSaving}>
                  {relsSaving ? 'Saving…' : `Save (${relsDeleted.size} removed, ${relsToAdd.length} added)`}
                </button>
                <button className="btn ghost" style={{ height: 30 }} onClick={cancelRels}>Cancel</button>
              </div>
            </div>
          ) : (
            <div style={{ padding: '4px 0' }}>
              {(term.relations || []).length === 0 ? (
                <div style={{ padding: '16px', color: 'var(--ink-3)', fontSize: 13, fontStyle: 'italic' }}>
                  No relations — click Edit to add one.
                </div>
              ) : term.relations.map((r, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px',
                  borderBottom: i < term.relations.length - 1 ? '1px solid var(--ice)' : 0,
                  fontSize: 13,
                }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--green)', flexShrink: 0 }} />
                  <span className="mono" style={{ color: 'var(--slate-d)' }}>{r.predicate}</span>
                  <span style={{ color: 'var(--ink-3)' }}>→</span>
                  <span style={{ color: 'var(--ink)', fontWeight: 500 }}>{r.object_label}</span>
                  {r.object_uri && (
                    <span className="mono" style={{ color: 'var(--ink-3)', fontSize: 11 }}>{r.object_uri.split('/').pop()}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Metadata */}
        <div className="card">
          <div className="card-h"><h3>Metadata</h3></div>
          <div className="card-b">
            <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr', gap: '8px 16px', fontSize: 13 }}>
              {[
                ['URI',         <span className="mono" style={{ color: 'var(--ink-2)' }}>{term.term_uri}</span>],
                ['Scheme',      term.scheme_label || '—'],
                ['Approved by', term.approved_by  || '—'],
                ['Source',      term.source_system || '—'],
                ['Document',    term.document_id  || '—'],
                ['Version',     <span className="pill">v{term.version}</span>],
              ].map(([k, v]) => (
                <>
                  <span key={`k-${k}`} style={{ color: 'var(--ink-3)' }}>{k}</span>
                  <span key={`v-${k}`} style={{ color: 'var(--ink)' }}>{v}</span>
                </>
              ))}
            </div>
          </div>
        </div>

        {/* Transition */}
        {nextStatuses.length > 0 && (
          <div className="card">
            <div className="card-h"><h3>Transition status</h3></div>
            <div className="card-b" style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <input
                value={actor}
                onChange={e => setActor(e.target.value)}
                placeholder="Your name (optional)"
                style={{
                  height: 32, padding: '0 10px', border: '1px solid var(--ice)',
                  borderRadius: 'var(--r)', background: 'var(--surface)',
                  font: '400 13px var(--font-sans)', color: 'var(--ink)', outline: 'none',
                }}
              />
              {nextStatuses.map(s => (
                <button key={s} className="btn" onClick={() => transition(s)}
                  style={{ textTransform: 'capitalize' }}>
                  → {s}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  )
}
