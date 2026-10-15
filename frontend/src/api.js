async function json(res) {
  if (!res.ok) {
    let msg = res.statusText
    try { msg = (await res.json()).detail || msg } catch { /* not JSON */ }
    throw new Error(msg)
  }
  return res.json()
}

export const listJobs = () => fetch('/api/jobs').then(json)
export const getJob = (id) => fetch(`/api/jobs/${id}`).then(json)
export const deleteJob = (id) => fetch(`/api/jobs/${id}`, { method: 'DELETE' }).then(json)

// XHR instead of fetch so we can report upload progress
export function uploadAudio(file, language, onProgress) {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('file', file)
    form.append('language', language || '')
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/jobs')
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total)
    xhr.onload = () => {
      let body = {}
      try { body = JSON.parse(xhr.responseText) } catch { /* ignore */ }
      xhr.status < 300 ? resolve(body) : reject(new Error(body.detail || `Upload failed (${xhr.status})`))
    }
    xhr.onerror = () => reject(new Error('Could not reach the server'))
    xhr.send(form)
  })
}
