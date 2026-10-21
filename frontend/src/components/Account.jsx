import { useEffect, useState } from 'react'
import { billingConfig, getToken, ledger, login, logout, me, setToken, signup } from '../api'

// Renders inside a header account chip; shows signin form when anonymous
// and balance + buy link when signed in. Landing page gets the big version.
export default function Account({ onUser }) {
  const [user, setUser] = useState(null)          // {email, balance,...} or null
  const [billing, setBilling] = useState(null)    // {enabled, bundles,...}
  const [mode, setMode] = useState('signin')      // signin | signup
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    billingConfig().then(setBilling).catch(() => setBilling({ enabled: false }))
    if (getToken()) me().then((u) => { setUser(u); onUser?.(u) }).catch(() => setToken(''))
  }, [])

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      const fn = mode === 'signup' ? signup : login
      const r = await fn(email, password)
      setToken(r.token); setUser(r); onUser?.(r)
      setPassword('')
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  const signout = async () => {
    try { await logout() } catch { /* session may be gone already */ }
    setToken(''); setUser(null); onUser?.(null)
  }

  return (
    <div className="account">
      {billing?.enabled && user ? (
        <div className="account-card">
          <div className="account-row">
            <span className="account-email">{user.email}</span>
            <button className="btn ghost" onClick={signout}>Sign out</button>
          </div>
          <div className="account-row">
            <span><strong id="credit-balance">{user.balance?.toFixed(1) ?? '0'}</strong> minutes left</span>
          </div>
          {billing.bundles?.length > 0 && <a className="btn" href="/#pricing">Buy credits</a>}
          <CreditLedger />
        </div>
      ) : billing?.enabled ? (
        <form className="account-card" onSubmit={submit}>
          <div className="account-tabs">
            <button type="button" className={mode === 'signin' ? 'tab on' : 'tab'} onClick={() => setMode('signin')}>Sign in</button>
            <button type="button" className={mode === 'signup' ? 'tab on' : 'tab'} onClick={() => setMode('signup')}>Create account</button>
          </div>
          {mode === 'signup' && <p className="hint">New accounts start with {billing.free_minutes ?? 30} free minutes.</p>}
          <input type="email" required placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} />
          <input type="password" required minLength={8} placeholder="Password (8+ characters)" value={password} onChange={(e) => setPassword(e.target.value)} />
          {error && <p className="error" role="alert">{error}</p>}
          <button className="btn" disabled={busy}>{busy ? '…' : mode === 'signup' ? 'Create account' : 'Sign in'}</button>
        </form>
      ) : null}
    </div>
  )
}

function CreditLedger() {
  const [rows, setRows] = useState(null)
  useEffect(() => { if (getToken()) ledger().then(setRows).catch(() => setRows([])) }, [])
  if (!rows?.length) return null
  return (
    <details className="ledger">
      <summary>Recent credit activity</summary>
      <ul>
        {rows.map((r, i) => (
          <li key={i}>
            <span className={`kind ${r.kind}`}>{r.kind}</span> {r.minutes > 0 ? '+' : ''}{r.minutes.toFixed(1)} min
            {r.note ? <span className="hint"> — {r.note}</span> : null}
          </li>
        ))}
      </ul>
    </details>
  )
}
