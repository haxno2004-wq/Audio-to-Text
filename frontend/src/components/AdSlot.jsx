import { useEffect, useRef, useState } from 'react'

// Loads the AdSense script once per page and renders an ad unit.
// Policy-safe: only shown on non-private pages (landing/pricing/footer of the
// result view), never inside transcript bodies or account screens.
// Fully config-driven: when ADSENSE_CLIENT is not set server-side, this
// renders nothing — so self-hosted/preview deployments stay ad-free.

const SCRIPT_ID = 'adsense-loader'

export function useAdsConfig() {
  const [cfg, setCfg] = useState(null)
  useEffect(() => {
    fetch('/api/ads/config').then(r => r.json()).then(setCfg)
      .catch(() => setCfg({ enabled: false }))
  }, [])
  return cfg
}

export default function AdSlot({ slot, className = '' }) {
  const cfg = useAdsConfig()
  const pushed = useRef(false)

  useEffect(() => {
    if (!cfg?.enabled || !slot || document.getElementById(SCRIPT_ID)) return
    const s = document.createElement('script')
    s.id = SCRIPT_ID
    s.async = true
    s.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${cfg.client}`
    s.crossOrigin = 'anonymous'
    document.head.appendChild(s)
  }, [cfg, slot])

  // Tell AdSense to fill this unit once it exists (script loaded first).
  useEffect(() => {
    if (!cfg?.enabled || !slot || pushed.current) return
    const t = setTimeout(() => {
      try { (window.adsbygoogle = window.adsbygoogle || []).push({}) ; pushed.current = true }
      catch { /* not loaded yet (blocked or slow) — leave space, no error */ }
    }, 300)
    return () => clearTimeout(t)
  }, [cfg, slot])

  if (!cfg?.enabled || !slot) return null

  return (
    <ins
      className={`adsbygoogle adslot ${className}`}
      style={{ display: 'block' }}
      data-ad-client={cfg.client}
      data-ad-slot={slot}
      data-ad-format="auto"
      data-full-width-responsive="true"
      aria-hidden="true"
    />
  )
}
