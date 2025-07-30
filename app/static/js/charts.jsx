const { useState, useEffect } = React;
const { Draggable }        = ReactDraggable;
const { ResizableBox }     = ReactResizable;

function ClientChartModal({ client, onClose }) {
  const [ html, setHtml ] = useState('<p>Loading…</p>');
  const [ scale, setScale ] = useState(1);

  useEffect(() => {
    fetch(`/charts/client/${encodeURIComponent(client)}`)
      .then(r => r.text())
      .then(setHtml)
      .catch(() => setHtml('<p class="text-red-600">Failed to load chart.</p>'));
  }, [client]);

  return (
    <Draggable handle=".modal-header">
      <ResizableBox
        width={600}
        height={500}
        minConstraints={[300, 300]}
        maxConstraints={[window.innerWidth-100, window.innerHeight-100]}
      >
        <div className="modal-window bg-white rounded shadow-lg flex flex-col">
          <div className="modal-header flex justify-between items-center bg-gray-100 p-2 cursor-move">
            <h2 className="text-lg font-bold">{client} – Training Chart</h2>
            <button onClick={onClose} className="text-2xl">×</button>
          </div>
          <div className="p-4 overflow-auto flex-1 space-y-4">
            <div
              className="zoom-wrapper"
              style={{ transform: `scale(${scale})`, transformOrigin: '0 0' }}
              dangerouslySetInnerHTML={{ __html: html }}
            />
          </div>
          <div className="p-2 border-t flex items-center gap-2">
            <button onClick={() => setScale(s => Math.max(.5, s - .1))} className="px-2 py-1 border rounded">−</button>
            <input
              type="range"
              min="50" max="300" step="10"
              value={scale * 100}
              onChange={e => setScale(e.target.value/100)}
              className="flex-1"
            />
            <span className="w-12 text-center">{Math.round(scale*100)}%</span>
            <button onClick={() => setScale(s => Math.min(3, s + .1))} className="px-2 py-1 border rounded">+</button>
          </div>
        </div>
      </ResizableBox>
    </Draggable>
  );
}
