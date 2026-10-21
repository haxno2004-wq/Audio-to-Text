import { useState } from 'react'
import AdSlot from './AdSlot.jsx'
import ModelsPanel from './ModelsPanel.jsx'

const NO_SPACE = /[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\u0e00-\u0eff\u1000-\u109f\u1780-\u17ff\u3000-\u303f\uff00-\uffef]/
const needsSpace = (a, b) => !(NO_SPACE.test(a.slice(-1)) && NO_SPACE.test(b[0]))

export function stamp(sec) {
  const s = Math.floor(sec)
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60
  const mm = String(m).padStart(h ? 2 : 1, '0'), rr = String(r).padStart(2, '0')
  return h ? `${h}:${mm}:${rr}` : `${mm}:${rr}`
}

function Words({ words, mark }) {
  const out = []
  words.forEach(([text, agree, alts], i) => {
    if (i > 0 && needsSpace(words[i - 1][0], text)) out.push(' ')
    if (mark && agree < 0.6) {
      const tip = alts?.length ? `Other models heard: ${alts.join('; ')}` : 'The models disagreed here'
      out.push(<span key={i} className="unsure" title={tip} tabIndex={0}>{text}</span>)
    } else out.push(text)
  })
  return out
}

function People({ speakers }) {
  const voices = [...new Set(speakers.map((b) => b.speaker))]
  return (
    <>
      <div className="persons">
        {voices.map((n) => (
          <span className="chip" data-n={n} key={n}>
            <span className="swatch" /> Person {n}
          </span>
        ))}
      </div>
      <article className="sheet dialogue">
        {speakers.map((b, i) => (
          <div className="turn" data-person={b.speaker} key={i}>
            <span className="who">Person {b.speaker}</span>
            <span className="bubble">{b.text}</span>
            <time className="num">{stamp(b.start)} → {stamp(b.end)}</time>
          </div>
        ))}
      </article>
    </>
  )
}

export default function Transcript({ job }) {
  const { final, models, failed, polished } = job.result
  const [mark, setMark] = useState(true)
  const [copied, setCopied] = useState(false)
  const [view, setView] = useState('transcript')
  const [variant, setVariant] = useState('ai') // ai-polished text vs raw consensus

  const polishedText = polished?.trim()
  const showVariant = polishedText && polishedText !== (job.final_text ?? final.text).trim()

  function speakersOf(f) {
    return f?.speakers?.length ? f.speakers : null
  }
  const speakers = speakersOf(final)

  const copyText = async () => {
    const text = view === 'transcript' ? bodyText : speakers.map((b) => `Person ${b.speaker}: ${b.text}`).join('\n\n')
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1600)
  }
  const unsure = (final.segments || []).reduce((n, s) => n + (s.words || []).filter((w) => w[1] < 0.6).length, 0)

  return (
    <section>
      <header className="t-head">
        <div>
          <h1 className="t-title">{job.filename}</h1>
          <p className="hint num">
            {stamp(job.duration)} long{final.language ? `, ${final.language}` : ''}
            {models.length > 1 ? `, merged from ${models.length} models` : ', one model finished'}
          </p>
        </div>
        <div className="actions">
          <button className="btn" onClick={copyText}>{copied ? 'Copied' : 'Copy text'}</button>
          <a className="btn ghost" href={`/api/jobs/${job.id}/transcript.txt`}>Download .txt</a>
        </div>
      </header>

      {speakers && (
        <div className="tabs" role="tablist">
          <button className={view === 'transcript' ? 'on' : ''} onClick={() => setView('transcript')} role="tab" aria-selected={view === 'transcript'}>Transcript</button>
          <button className={view === 'people' ? 'on' : ''} onClick={() => setView('people')} role="tab" aria-selected={view === 'people'}>People</button>
        </div>
      )}
      {models.length === 1 && (
        <p className="notice slim">Only one model returned a transcript, so no cross-check happened.</p>
      )}

      {view === 'transcript' && (
        <>
          {showVariant && (
            <div className="pillbar">
              <button className={`pill${variant === 'ai' ? ' on' : ''}`} onClick={() => setVariant('ai')}>✦ AI-corrected</button>
              <button className={`pill${variant === 'raw' ? ' on' : ''}`} onClick={() => setVariant('raw')}>Raw consensus</button>
            </div>
          )}
          {models.length > 1 && (
            <label className="check">
              <input type="checkbox" checked={mark} onChange={(e) => setMark(e.target.checked)} />
              Underline disagreed words{` (${unsure})`}
            </label>
          )}
          <article className="sheet">
            {(final.segments || []).map((s) => (
              <div className="seg" key={s.start}>
                <time className="num">{stamp(s.start)}</time>
                <p><Words words={s.words} mark={mark && models.length > 1} /></p>
              </div>
            ))}
          </article>
        </>
      )}

      {view === 'people' && speakers && <People speakers={speakers} />}

      <ModelsPanel models={models} failed={failed} />
      <AdSlot slot={import.meta.env.VITE_AD_SLOT_FOOTER} className="after-results" />
    </section>
  )
}
