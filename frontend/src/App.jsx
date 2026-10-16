import { useCallback, useEffect, useState } from 'react'
import { clearHistory, deleteJob, getJob, listJobs, uploadAudio } from './api'
import History from './components/History.jsx'
import UploadPanel from './components/UploadPanel.jsx'
import Progress from './components/Progress.jsx'
import Transcript from './components/Transcript.jsx'

export default function App() {
  const [jobs, setJobs] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [job, setJob] = useState(null)
  const [upload, setUpload] = useState(null) // { name, pct } while the file is going up
  const [error, setError] = useState('')

  const refresh = useCallback(() => listJobs().then(setJobs).catch(() => {}), [])
  useEffect(() => { refresh() }, [refresh])

  // Poll the active job until it finishes
  useEffect(() => {
    if (!activeId) { setJob(null); return }
    let stop = false
    let timer
    const tick = async () => {
      try {
        const j = await getJob(activeId)
        if (stop) return
        setJob(j)
        if (j.status === 'queued' || j.status === 'processing') timer = setTimeout(tick, 1500)
        else refresh()
      } catch (e) { if (!stop) setError(e.message) }
    }
    tick()
    return () => { stop = true; clearTimeout(timer) }
  }, [activeId, refresh])

  const onFile = async (file, language) => {
    setError('')
    setUpload({ name: file.name, pct: 0 })
    try {
      const { id } = await uploadAudio(file, language, (pct) => setUpload({ name: file.name, pct }))
      setUpload(null)
      setActiveId(id)
      refresh()
    } catch (e) {
      setUpload(null)
      setError(e.message)
    }
  }

  const onDelete = async (id) => {
    try { await deleteJob(id) } catch (e) { setError(e.message); return }
    if (id === activeId) setActiveId(null)
    refresh()
  }

  const onClearAll = async () => {
    try { await clearHistory() } catch (e) { setError(e.message); return }
    setActiveId(null)
    refresh()
  }

  const running = job && (job.status === 'queued' || job.status === 'processing')

  let main
  if (upload) main = <Progress title={`Uploading ${upload.name}`} stage="Uploading" pct={upload.pct} />
  else if (activeId && !job) main = <p className="hint">Loading…</p>
  else if (running) main = <Progress title={job.filename} stage={job.stage} pct={job.progress} />
  else if (job?.status === 'failed') {
    main = (
      <section className="notice" role="alert">
        <h2>This file couldn't be transcribed</h2>
        <p>{job.error}</p>
        <button className="btn" onClick={() => setActiveId(null)}>Try another file</button>
      </section>
    )
  } else if (job?.status === 'done') main = <Transcript job={job} />
  else main = <UploadPanel onFile={onFile} />

  return (
    <div className="shell">
      <History jobs={jobs} activeId={activeId} onSelect={setActiveId} onNew={() => setActiveId(null)} onDelete={onDelete} onClearAll={onClearAll} />
      <main className="main">
        {error && <p className="error" role="alert">{error}</p>}
        {main}
      </main>
    </div>
  )
}
