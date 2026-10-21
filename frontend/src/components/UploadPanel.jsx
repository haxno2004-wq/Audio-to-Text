import { useRef, useState } from 'react'

const LANGS = [
  ['', 'Detect automatically'], ['en', 'English'], ['hi', 'Hindi'], ['ta', 'Tamil'], ['te', 'Telugu'],
  ['ml', 'Malayalam'], ['kn', 'Kannada'], ['bn', 'Bengali'], ['mr', 'Marathi'], ['it', 'Italian'],
  ['de', 'German'], ['es', 'Spanish'], ['fr', 'French'], ['pt', 'Portuguese'], ['nl', 'Dutch'],
  ['ru', 'Russian'], ['tr', 'Turkish'], ['ar', 'Arabic'], ['ja', 'Japanese'], ['ko', 'Korean'], ['zh', 'Chinese'],
]

export default function UploadPanel({ onFile }) {
  const input = useRef(null)
  const [drag, setDrag] = useState(false)
  const [language, setLanguage] = useState('')
  const [mode, setMode] = useState('full')

  const take = (files) => { if (files && files[0]) onFile(files[0], language, mode) }

  return (
    <section>
      <h1>Turn a recording into text</h1>
      <p className="lede">Add any audio file. Several speech models listen to it and the result is merged into one transcript.</p>

      <div
        className={`drop${drag ? ' over' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); take(e.dataTransfer.files) }}
      >
        <p className="drop-title">Drop an audio file here</p>
        <p className="hint">mp3, wav, m4a, flac, ogg, opus, aac, webm and most video files with sound</p>
        <button className="btn" onClick={() => input.current.click()}>Choose a file</button>
        <input ref={input} type="file" hidden accept="audio/*,video/*,.m4a,.flac,.opus,.amr,.wma" onChange={(e) => take(e.target.files)} />
      </div>

      <div className="field row">
        <label className="field">
          <span>Language</span>
          <select value={language} onChange={(e) => setLanguage(e.target.value)}>
            {LANGS.map(([code, name]) => <option key={code} value={code}>{name}</option>)}
          </select>
          <span className="hint">Leave on automatic unless detection keeps getting it wrong.</span>
        </label>
        <label className="field">
          <span>Accuracy mode</span>
          <select value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="full">Maximum accuracy — every model votes</option>
            <option value="budget">Budget — 2 models, lower cost</option>
          </select>
          <span className="hint">Budget mode still anchors on the two strongest Tamil models.</span>
        </label>
      </div>
    </section>
  )
}
