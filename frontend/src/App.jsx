import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Inbox from './pages/Inbox'
import Glossary from './pages/Glossary'
import Pipeline from './pages/Pipeline'
import TermDetail from './pages/TermDetail'
import Stats from './pages/Stats'
import AuditLog from './pages/AuditLog'
import Graph from './pages/Graph'
import Miro from './pages/Miro'

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex min-h-screen">
        <Sidebar />
        <main className="flex-1 overflow-auto">
          <Routes>
            <Route path="/" element={<Inbox />} />
            <Route path="/pipeline" element={<Pipeline />} />
            <Route path="/glossary" element={<Glossary />} />
            <Route path="/stats" element={<Stats />} />
            <Route path="/graph" element={<Graph />} />
            <Route path="/audit" element={<AuditLog />} />
            <Route path="/miro" element={<Miro />} />
            <Route path="/terms/*" element={<TermDetail />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
