export default function Miro() {
  const miroUrl =
    'https://miro.com/app/live-embed/uXjVHYUAwCA=/' +
    '?embedMode=view_only_without_ui' +
    '&moveToViewport=-512,-253,1024,504' +
    '&embedId=742433091738'

  return (
    <div className="flex flex-col h-full p-8">
      <h1 className="text-2xl font-semibold text-gray-900 mb-1">Miro Board</h1>
      <p className="text-sm text-gray-500 mb-4">Collaborative whiteboard for ontology design.</p>
      <div className="flex-1 rounded-xl overflow-hidden border border-gray-200 min-h-[600px]">
        <iframe
          src={miroUrl}
          className="w-full h-full"
          style={{ minHeight: 600 }}
          allow="fullscreen; clipboard-read; clipboard-write"
          allowFullScreen
        />
      </div>
    </div>
  )
}
