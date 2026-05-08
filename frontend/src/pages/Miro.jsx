export default function Miro() {
  const miroUrl =
    'https://miro.com/app/live-embed/uXjVHYUAwCA=/' +
    '?embedMode=view_only_without_ui' +
    '&moveToViewport=-512,-253,1024,504' +
    '&embedId=742433091738'

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Miro Board</h1>
          <div className="sub">Collaborative whiteboard for ontology design and stakeholder review.</div>
        </div>
        <div className="actions">
          <a href="https://miro.com" target="_blank" rel="noopener noreferrer" className="btn">
            <ExtIcon /> Open in Miro
          </a>
        </div>
      </div>

      <div className="card" style={{ overflow: 'hidden' }}>
        <iframe
          src={miroUrl}
          style={{ display: 'block', width: '100%', height: 'calc(100vh - 220px)', minHeight: 500, border: 0 }}
          allow="fullscreen; clipboard-read; clipboard-write"
          allowFullScreen
          title="Miro board"
        />
      </div>
    </>
  )
}

const ExtIcon = () => (
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 3h4v4M13 3 7 9M7 4H4a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h7a1 1 0 0 0 1-1V9"/>
  </svg>
)
