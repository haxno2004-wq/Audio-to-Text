import { useEffect, useState } from 'react'
import { billingConfig, createOrder, createStripeOrder,
         payWithRazorpay, verifyPayment, verifyStripe } from '../api'
import AdSlot from './AdSlot.jsx'
import Reward from './Reward.jsx'

const INR = (paise) => `₹${(paise / 100).toLocaleString('en-IN')}`

export default function Pricing({ user, onUser }) {
  const [cfg, setCfg] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    billingConfig().then(setCfg).catch(() => setCfg({ enabled: false }))
  }, [])

  // Stripe checkout redirect lands here: #stripe-paid&order=lo_..&session_id=..
  // Verify the payment server-side, refresh the balance, clean up the hash.
  useEffect(() => {
    if (!location.hash.startsWith('#stripe-paid') || !user) return
    const q = new URLSearchParams(location.hash.split('&').slice(1).join('&'))
    const order = q.get('order')
    const sessionId = q.get('session_id')
    history.replaceState(null, '', '#pricing')
    if (!order || !sessionId) return
    verifyStripe(order, sessionId)
      .then((out) => {
        onUser?.({ ...user, balance: out.balance })
        setNotice(out.credited === false
          ? 'This payment was already credited.'
          : `Payment received — your account now has ${out.balance.toFixed(1)} minutes.`)
      })
      .catch((e) => setError(e.message))
  }, [user])

  if (!cfg) return null
  const signedIn = Boolean(cfg.enabled && user)
  const raz = cfg.razorpay_available !== false
  const stripe = cfg.stripe_available === true

  const buyRazorpay = async (bundleName) => {
    setError(''); setBusy(`raz-${bundleName}`)
    try {
      const order = await createOrder(bundleName)
      const resp = await payWithRazorpay(order)
      const out = await verifyPayment(order.order, resp.razorpay_order_id,
        resp.razorpay_payment_id, resp.razorpay_signature)
      if (out.balance != null) onUser?.({ ...user, balance: out.balance })
      setNotice(out.credited === false ? 'Credits were already added for this order.' :
        `Payment received — your account now has ${out.balance.toFixed(1)} minutes.`)
    } catch (e) { setError(e.message) }
    finally { setBusy('') }
  }

  const buyWithStripe = async (bundleName) => {
    setError(''); setBusy(`st-${bundleName}`)
    try {
      const order = await createStripeOrder(bundleName)
      location.assign(order.url)   // Stripe Checkout is a hosted redirect page
    } catch (e) { setError(e.message); setBusy('') }
  }

  return (
    <section id="pricing" className="pricing">
      <h2>Pricing</h2>
      <p className="lede">Prepaid — pay for minutes, not subscriptions. One minute of audio uses one credit, and failed jobs never charge you.</p>
      {cfg.enabled
        ? (signedIn || <p className="hint">Sign in above to buy credits; new accounts start with {cfg.free_minutes ?? 30} free minutes.</p>)
        : <p className="hint">Payments are not enabled on this deployment yet (set BILLING_ENABLED=1 plus gateway keys).</p>}
      <div className="bundles">
        {(cfg.bundles || []).map((b) => (
          <div className="bundle" key={b.name}>
            <h3>{b.label}</h3>
            <p className="price">{INR(b.amount_paise)}</p>
            <p className="hint">≈ {Math.round(b.amount_paise / 100 / Math.max(b.minutes, 1) * 60)}% cheaper than most transcription sites</p>
            {signedIn ? (
              <div className="gateway-row">
                {raz && (
                  <button className="btn" disabled={busy === `raz-${b.name}`} onClick={() => buyRazorpay(b.name)}>
                    {busy === `raz-${b.name}` ? 'Opening…' : (stripe ? 'Buy with Razorpay' : 'Buy')}
                  </button>
                )}
                {stripe && (
                  <button className={`btn${raz ? ' ghost' : ''}`} disabled={busy === `st-${b.name}`}
                          onClick={() => buyWithStripe(b.name)}>
                    {busy === `st-${b.name}` ? 'Redirecting…' : (raz ? 'Buy with Stripe' : 'Buy')}
                  </button>
                )}
              </div>
            ) : <a className="btn ghost" href="/">Sign in first</a>}
          </div>
        ))}
      </div>
      <Reward user={user} onUser={onUser} />
      {notice && <p className="hint ok-note">{notice}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      <AdSlot slot={import.meta.env.VITE_AD_SLOT_PRICING} className="under-pricing" />
    </section>
  )
}
