const when = (t) => new Date(t * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
const label = { queued: 'Waiting', processing: 'Working', failed: 'Failed', done: '' }

export default function History({ jobs, activeId, onSelect, onNew, onDelete, onClearAll }) {
  const removable = jobs.filter((j) => j.status === 'done' || j.status === 'failed').length

  const clear = () => {
    const n = removable === jobs.length
      ? `${removable} transcriptions`
      : `${removable} finished transcriptions (${jobs.length - removable} still running will be kept)`
    if (removable > 0 && confirm(`Delete ${n}? This cannot be undone.`)) onClearAll()
  }

  return (
    <aside className="rail">
      <div>
        <p className="brand">Transcribe</p>
        <button className="btn block" onClick={onNew}>New transcription</button>
      </div>
      <nav aria-label="Past transcriptions" style={{ display: 'grid', gap: 6 }}>
        <p className="hint" style={{ paddingLeft: 6 }}>History</p>
        {jobs.length === 0 && <p className="hint" style={{ paddingLeft: 6 }}>Finished transcripts will appear here.</p>}
        <ul className="history">
          {jobs.map((j) => (
            <li key={j.id} className={j.id === activeId ? 'on' : ''}>
              <button className="pick" onClick={() => onSelect(j.id)} aria-current={j.id === activeId}>
                <span className="name">{j.filename}</span>
                <span className="meta">{when(j.created_at)}{label[j.status] ? ` · ${label[j.status]}` : ''}</span>
              </button>
              {(j.status === 'done' || j.status === 'failed') && (
                <button className="x" aria-label={`Delete ${j.filename}`} title="Delete" onClick={() => onDelete(j.id)}>×</button>
              )}
            </li>
          ))}
        </ul>
      </nav>
      <div className="rail-foot">
        <button className="btn danger tiny" disabled={removable === 0} onClick={clear}>Clear all history</button>
      </div>
    </aside>
  )
}
