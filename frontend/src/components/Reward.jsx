import { useEffect, useState } from 'react'
import { claimReward, rewardsConfig } from '../api'

// "Watch an ad → earn free minutes" card (how competitor sites monetise the
// free tier). Uses Google's web *rewarded* ad format via the GPT tag, which is
// the only incentive-compatible format AdSense/GAM allows (incentivising
// normal display banners breaches policy). Configure with TWO frontend env
// vars from your Google Ad Manager dashboard:
//   VITE_REWARDED_NETWORK_ID  e.g. 6355419
//   VITE_REWARDED_AD_UNIT     e.g. rewarded_transcriber
// When neither is set the card still works — you just skip straight to the
// credit-granting API, whose per-account + per-IP daily cap keeps abuse down
// (server-side ad-view verification is not offered by Google, this is the
// accepted approximation).

const NETWORK = import.meta.env.VITE_REWARDED_NETWORK_ID || ''
const UNIT = import.meta.env.VITE_REWARDED_AD_UNIT || ''
const GPT_SCRIPT_ID = 'gpt-tag-loader'
const GPT_SRC = 'https://securepubads.g.doubleclick.net/tag/js/gpt.js'

function loadGpt() {
  if (document.getElementById(GPT_SCRIPT_ID)) return
  const s = document.createElement('script')
  s.id = GPT_SCRIPT_ID
  s.async = true
  s.src = GPT_SRC
  document.head.appendChild(s)
}

// Opens a full-screen rewarded ad. Resolves 'done' (user saw it, ad closed)
// or 'unavailable' (no ad unit configured, or the tag couldn't load — e.g.
// an ad blocker). We never claim before close.
function showRewarded() {
  return new Promise((resolve) => {
    if (!NETWORK || !UNIT) { resolve('unavailable'); return }
    loadGpt()
    window.googletag = window.googletag || { cmd: [] }
    window.googletag.cmd.push(() => {
      const gt = window.googletag
      const pub = gt.pubads()
      let settled = false
      const finish = (why) => { if (!settled) { settled = true; resolve(why) } }
      pub.addEventListener('rewardedSlotReady', (e) => e.makeRewardedVisible())
      pub.addEventListener('rewardedSlotClosed', (e) => {
        try { gt.destroySlots([e.slot]) } catch { /* ignore */ }
        finish('done')
      })
      let slot
      try {
        slot = gt.defineOutOfPageSlot(`/${NETWORK}/${UNIT}`, gt.enums.OutOfPageFormat.REWARDED)
      } catch { slot = null }
      if (!slot) { finish('unavailable'); return }
      slot.addService(pub)
      gt.enableServices()
      gt.display(slot)
      // Safety net: if neither event fires (blocked), resolve on click-away
      setTimeout(() => finish('done'), 90_000)
    })
  })
}

export default function Reward({ user, onUser }) {
  const [cfg, setCfg] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => { rewardsConfig().then(setCfg).catch(() => setCfg({ enabled: false })) }, [])

  if (!cfg?.enabled) return null
  const minutes = cfg.minutes

  const watch = async () => {
    setBusy(true); setMsg('')
    try {
      const how = await showRewarded()
      const out = await claimReward()
      onUser?.({ ...user, balance: out.balance })
      const plural = out.credited === 1 ? '' : 's'
      setMsg(`+${out.credited} minute${plural} added — your balance is ${out.balance.toFixed(1)}`)
    } catch (e) {
      setMsg(e.message)
    } finally { setBusy(false) }
  }

  return (
    <section className="reward">
      <div className="reward-card">
        <div>
          <h3>Short on credits? <span className="ad-tag">Sponsored · rewarded ad</span></h3>
          <p className="hint">
            Watch a short ad and we'll add {minutes} free transcription minute{minutes === 1 ? '' : 's'} to your account.
            {cfg.remaining != null && (cfg.remaining > 0
              ? ` ${cfg.remaining} of ${cfg.daily_cap} rewards left today.`
              : ` Today's rewards are used up — back tomorrow.`)}
          </p>
          {msg && <p className="hint">{msg}</p>}
        </div>
        <button className="btn ghost" disabled={busy || cfg.remaining === 0} onClick={watch}>
          {busy ? 'Opening ad…' : `Watch ad → +${minutes} min`}
        </button>
      </div>
    </section>
  )
}
