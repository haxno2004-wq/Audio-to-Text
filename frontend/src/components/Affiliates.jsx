import { useEffect, useState } from 'react'

// Disclosure-safe affiliate block. Renders nothing until AFFILIATE_LINKS is
// set server-side (.env), so self-hosted/local use shows no third-party
// promotions. Every link is labelled as an ad/affiliation *next to the links*
// (FTC Endorsement Guides + ASCI influencer rules: the disclosure must sit
// with the recommendation, not only in a footer). Links use rel="sponsored
// noopener" per Google's link-spam guidance.
export default function Affiliates() {
  const [links, setLinks] = useState([])
  useEffect(() => {
    fetch('/api/affiliates/config').then(r => r.json())
      .then(cfg => setLinks(cfg.links || []))
      .catch(() => setLinks([]))
  }, [])
  if (!links.length) return null
  return (
    <section className="affiliates" aria-label="Recommended tools (affiliate)">
      <h2>Recommended tools</h2>
      <p className="disclosure">
        <strong>Ad / affiliate:</strong> if you buy through a link below we may earn a
        commission at no extra cost to you. Only tools relevant to transcription or
        improving recordings appear here.
      </p>
      <div className="aff-list">
        {links.map((l) => (
          <a className="aff-card" key={l.url} href={l.url} target="_blank" rel="sponsored noopener">
            <span className="aff-name">{l.name}</span>
            <span className="aff-note">{l.note}</span>
          </a>
        ))}
      </div>
    </section>
  )
}
