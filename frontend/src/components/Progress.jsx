export default function Progress({ title, stage, pct }) {
  const p = Math.round(Math.min(1, Math.max(0, pct)) * 100)
  return (
    <section className="progress" aria-live="polite">
      <h2>{title}</h2>
      <div className="bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow={p} aria-label={stage}>
        <span style={{ width: `${p}%` }} />
      </div>
      <p className="progress-meta"><span>{stage}</span><span className="num">{p}%</span></p>
      <p className="hint">You can close this tab. The transcript will be waiting in your history.</p>
    </section>
  )
}
