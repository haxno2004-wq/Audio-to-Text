const TOKEN_KEY = 'td_token'

export function getToken() { return localStorage.getItem(TOKEN_KEY) || '' }
export function setToken(t) { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) }

function authHeaders(extra = {}) {
  const t = getToken()
  return t ? { Authorization: `Bearer ${t}`, ...extra } : { ...extra }
}

async function json(res) {
  if (!res.ok) {
    let msg = res.statusText
    try {
      const body = await res.json()
      msg = typeof body.detail === 'string' ? body.detail : msg
    } catch { /* not JSON */ }
    throw new Error(msg)
  }
  return res.json()
}

export const listJobs = () => fetch('/api/jobs').then(json)
export const getJob = (id) => fetch(`/api/jobs/${id}`).then(json)
export const deleteJob = (id) => fetch(`/api/jobs/${id}`, { method: 'DELETE' }).then(json)
export const clearHistory = () => fetch('/api/jobs', { method: 'DELETE' }).then(json)
export const billingConfig = () => fetch('/api/billing/config').then(json)

// ---- accounts ----
export function signup(email, password) {
  const form = new FormData()
  form.append('email', email); form.append('password', password)
  return fetch('/api/auth/signup', { method: 'POST', body: form }).then(json)
}
export function login(email, password) {
  const form = new FormData()
  form.append('email', email); form.append('password', password)
  return fetch('/api/auth/login', { method: 'POST', body: form }).then(json)
}
export function logout() {
  return fetch('/api/auth/logout', { method: 'POST', headers: authHeaders() }).then(json)
}
export const me = () => fetch('/api/auth/me', { headers: authHeaders() }).then(json)
export const ledger = () => fetch('/api/auth/ledger', { headers: authHeaders() }).then(json)

// ---- billing ----
export function createOrder(bundleName) {
  const form = new FormData()
  form.append('bundle', bundleName)
  return fetch('/api/billing/order', { method: 'POST', body: form, headers: authHeaders() }).then(json)
}
export function verifyPayment(order, rzOrderId, rzPaymentId, rzSignature) {
  const form = new FormData()
  form.append('order', order)
  form.append('razorpay_order_id', rzOrderId)
  form.append('razorpay_payment_id', rzPaymentId)
  form.append('razorpay_signature', rzSignature)
  return fetch('/api/billing/verify', { method: 'POST', body: form, headers: authHeaders() }).then(json)
}

// ---- Stripe (second gateway; the browser is redirected to Stripe Checkout,
// comes back with ?session_id=... in the hash, and we verify server-side) ----
export function createStripeOrder(bundleName) {
  const form = new FormData()
  form.append('bundle', bundleName)
  return fetch('/api/billing/stripe/order', { method: 'POST', body: form, headers: authHeaders() }).then(json)
}
export function verifyStripe(order, sessionId) {
  const form = new FormData()
  form.append('order', order)
  form.append('session_id', sessionId)
  return fetch('/api/billing/stripe/verify', { method: 'POST', body: form, headers: authHeaders() }).then(json)
}

// ---- rewards: watch an ad, earn free minutes ----
export const rewardsConfig = () => fetch('/api/rewards/config', { headers: authHeaders() }).then(json)
export function claimReward() {
  return fetch('/api/rewards/claim', { method: 'POST', headers: authHeaders() }).then(json)
}

// XHR instead of fetch so we can report upload progress
export function uploadAudio(file, language, mode, onProgress) {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('file', file)
    form.append('language', language || '')
    form.append('mode', mode || '')
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

// Loads Razorpay Checkout and opens it for an order, resolving the payment
// handler response (or throwing before the modal opens).
export function payWithRazorpay(order) {
  return new Promise((resolve, reject) => {
    const open = () => {
      const rz = new window.Razorpay({
        key: order.key_id,
        amount: order.amount,
        currency: order.currency,
        name: 'CallTranscript',
        description: `${order.minutes} transcription minutes`,
        order_id: order.razorpay_order_id,
        handler: (resp) => resolve(resp),
        prefill: {},
        theme: { color: '#2563eb' },
      })
      rz.on('payment.failed', () => reject(new Error('Payment failed — no credits were added')))
      rz.open()
    }
    if (window.Razorpay) { open(); return }
    const s = document.createElement('script')
    s.src = 'https://checkout.razorpay.com/v1/checkout.js'
    s.onload = open
    s.onerror = () => reject(new Error('Could not load the payment window'))
    document.head.appendChild(s)
  })
}
