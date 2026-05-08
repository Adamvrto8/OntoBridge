import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import { api } from './api/client'
import Inbox from './pages/Inbox'
import Glossary from './pages/Glossary'
import Pipeline from './pages/Pipeline'
import TermDetail from './pages/TermDetail'
import Stats from './pages/Stats'
import AuditLog from './pages/AuditLog'
import Graph from './pages/Graph'
import Miro from './pages/Miro'

export default function App() {
  const [counts, setCounts] = useState({})

  useEffect(() => {
    api.stats.get().then(s => {
      setCounts({
        'Governance Inbox': s.by_status?.review ?? 0,
        'My Reviews':       s.by_status?.review ?? 0,
        'Drafts':           s.by_status?.draft ?? 0,
        'Glossary Browser': s.by_status?.published ?? 0,
        'Audit Log':        s.recent_activity ?? 0,
      })
    }).catch(() => {})
  }, [])

  return (
    <BrowserRouter>
      <div className="flex min-h-screen">
        <Sidebar counts={counts} />
        <main className="flex-1 overflow-auto h-screen">
          <Routes>
            <Route path="/"         element={<Inbox />} />
            <Route path="/pipeline" element={<Pipeline />} />
            <Route path="/glossary" element={<Glossary />} />
            <Route path="/stats"    element={<Stats />} />
            <Route path="/graph"    element={<Graph />} />
            <Route path="/audit"    element={<AuditLog />} />
            <Route path="/miro"     element={<Miro />} />
            <Route path="/terms/*"  element={<TermDetail />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
