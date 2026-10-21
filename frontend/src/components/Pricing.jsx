import { useEffect, useState } from 'react'
import { billingConfig, createOrder, getToken, payWithRazorpay, verifyPayment } from '../api'
import AdSlot from './AdSlot.jsx'

const INR = (paise) => `₹${(paise / 100).toLocaleString('en-IN')}`

export default function Pricing({ user, onUser }) {
  const [cfg, setCfg] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  useEffect(() => { billingConfig().then(setCfg).catch(() => setCfg({ enabled: false })) }, [])

  if (!cfg) return null
  const signedIn = Boolean(cfg.enabled && user)

  const buy = async (bundleName) => {
    setError(''); setBusy(bundleName)
    try {
      const order = await createOrder(bundleName)
      const resp = await payWithRazorpay(order)
      const out = await verifyPayment(order.order, resp.razorpay_order_id,
        resp.razorpay_payment_id, resp.razorpay_signature)
      if (out.balance != null) onUser?.({ ...user, balance: out.balance })
      alert(out.credited === false ? 'Credits were already added for this order.' :
        `Payment received — your account now has ${out.balance.toFixed(1)} minutes.`)
    } catch (e) { setError(e.message) }
    finally { setBusy('') }
  }

  return (
    <section id="pricing" className="pricing">
      <h2>Pricing</h2>
      <p className="lede">Prepaid — pay for minutes, not subscriptions. One minute of audio uses one credit, and failed jobs never charge you.</p>
      {cfg.enabled
        ? (signedIn || <p className="hint">Sign in above to buy credits; new accounts start with {cfg.free_minutes ?? 30} free minutes.</p>)
        : <p className="hint">Payments are not enabled on this deployment yet (set BILLING_ENABLED=1 plus Razorpay keys).</p>}
      <div className="bundles">
        {(cfg.bundles || []).map((b) => (
          <div className="bundle" key={b.name}>
            <h3>{b.label}</h3>
            <p className="price">{INR(b.amount_paise)}</p>
            <p className="hint">≈ {Math.round(b.amount_paise / 100 / Math.max(b.minutes, 1) * 60)}% cheaper than most transcription sites</p>
            {signedIn
              ? <button className="btn" disabled={busy === b.name} onClick={() => buy(b.name)}>
                  {busy === b.name ? 'Opening payment…' : 'Buy'}
                </button>
              : <a className="btn ghost" href="/">Sign in first</a>}
          </div>
        ))}
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      <AdSlot slot={import.meta.env.VITE_AD_SLOT_PRICING} className="under-pricing" />
    </section>
  )
}
