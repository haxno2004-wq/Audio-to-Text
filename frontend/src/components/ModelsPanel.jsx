export default function ModelsPanel({ models, failed }) {
  return (
    <details className="models">
      <summary>Compare what each model heard</summary>
      <div className="cols">
        {models.map((m) => (
          <div className="col" key={m.name}>
            <h3>{m.label}</h3>
            <p className="hint num">
              {m.agreement != null ? `${Math.round(m.agreement * 100)}% match with final` : ''} · {m.elapsed}s
            </p>
            <p className="raw">{m.text}</p>
          </div>
        ))}
      </div>
      {failed.length > 0 && (
        <ul className="failed">
          {failed.map((f) => <li key={f.name}><strong>{f.label}</strong> did not finish: {f.error}</li>)}
        </ul>
      )}
    </details>
  )
}
