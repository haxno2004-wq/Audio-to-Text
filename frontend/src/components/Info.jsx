import { useEffect, useState } from 'react'
import { billingConfig } from '../api'

// Public info pages: FAQ, Privacy Policy, Terms of Service.
// Real, substantive content matters twice over here: users use it, and
// AdSense reviewers reject sites that only show a bare tool with no
// info pages. All copy below describes how THIS product actually works.

export const INFO_SECTIONS = ['faq', 'privacy', 'terms']

const CONTACT_EMAIL = 'haxno2004@gmail.com'
const SITE = 'CallTranscript'

function Faq() {
  return (
    <>
      <h2>Frequently asked questions</h2>
      <div className="faq">
        <h3>What does {SITE} do?</h3>
        <p>You upload a recorded call (mp3, wav, m4a, ogg, flac, webm or video files with audio), and within a few minutes you get an accurate text transcript. The service is optimised for Indian languages — especially Tamil — and supports calls with two or more speakers.</p>

        <h3>How accurate is it, really?</h3>
        <p>Instead of trusting a single speech-to-text engine, {SITE} runs your audio through several independent AI models at once (Sarvam AI, ElevenLabs Scribe, Groq Whisper, Deepgram and AssemblyAI where configured). Their word-level outputs are aligned, timestamped and then fused by a weighted vote — so a word must be agreed on by multiple models before it lands in your final transcript. Words the models disagree on are underlined in amber so you can check them yourself. On clear Tamil phone calls this consensus typically lands above 90% word accuracy; heavy crosstalk, strong accents or a bad phone line lower it, exactly as with human transcription.</p>

        <h3>Which languages are supported?</h3>
        <p>Tamil is the strongest supported language — it is the reason the multi-model consensus approach exists. Other Indian and international languages (Hindi, Telugu, English, and 50+ more) also work with whichever models cover them; the final transcript adopts the language of our highest-weighted model for your audio.</p>

        <h3>Do you separate the speakers?</h3>
        <p>Yes. When the models return speaker information, {SITE} merges their speaker segments — deciding which model's speaker timeline is most reliable and remapping the others onto it — and presents the call as a chat-style dialogue: Person 1, Person 2, and so on, each in a different colour.</p>

        <h3>What is “budget mode”?</h3>
        <p>Before uploading you can pick Full accuracy or Budget. Budget runs only our two cost-efficient models — it is around half the price of a full run with a small accuracy trade-off. Full mode runs every enabled model for the best possible consensus.</p>

        <h3>What is the “AI polish”? Can I turn it off?</h3>
        <p>The transcript is optionally passed through an AI language model that cleans up spoken-language spelling and punctuation without changing the wording — for example, names of people or places that sound the same but have ambiguous spelling. The raw, unpolished output of every model is always available under “Model comparison”, so nothing is hidden from you.</p>

        <h3>How do credits work? What happens if a job fails?</h3>
        <p>Credits are minutes of audio. New accounts start with free minutes. You only ever pay for successful transcripts: if a job fails for any reason (bad file, provider outage), no credit is deducted. When you run out, top up on the Pricing page — prepaid bundles, no subscription.</p>

        <h3>Can I earn free minutes instead of paying?</h3>
        <p>Yes — watch a short ad and we credit you free minutes (a few per day, see the offer on the pricing page). Voluntary, and never shown inside your transcripts.</p>

        <h3>Do you keep my recordings?</h3>
        <p>Uploads are stored only for the time it takes to produce the transcript, on our server, purely for that processing. You can delete any job (audio + transcript) from your history at any point, and “Clear history” removes all finished jobs immediately.</p>

        <h3>Is there an API?</h3>
        <p>Not yet. {SITE} is a self-service web app. Write to {CONTACT_EMAIL} if your business needs bulk transcription.</p>
      </div>
    </>
  )
}

function Privacy() {
  return (
    <>
      <h2>Privacy Policy</h2>
      <p className="hint">Last updated: October 2026</p>
      <div className="faq">
        <h3>What we collect</h3>
        <p><strong>Audio you upload.</strong> Stored on the server only while your transcription job runs. Once a job finishes (or fails), the audio file exists in your history solely for download/deletion by you, and is deleted when you delete the job or clear your history.</p>
        <p><strong>Transcripts.</strong> Kept in your history until you delete them, encrypted only insofar as our database store is, and never shared with third parties for advertising.</p>
        <p><strong>Account data.</strong> If you create an account: your email address, a salted and hashed version of your password (we do not store passwords in readable form), and your credit balance with its ledger. Session tokens keep you signed in for up to 30 days; signing out deletes the token.</p>
        <p><strong>Usage/troubleshooting logs.</strong> Standard server logs (which may include your IP address and upload size) retained only briefly for debugging and abuse prevention.</p>

        <h3>Third parties we process your data with</h3>
        <p>Your audio is sent to the speech-to-text providers you see in the model list (for example Sarvam AI, ElevenLabs, Groq, Deepgram, AssemblyAI). Each provider processes the audio to return text — their data policies apply to that processing step. The tasks are one-off and we do not retain copies on our side after a job is done.</p>
        <p>When you buy credits your payment is processed by Razorpay or Stripe. {SITE} never sees or stores your full card details.</p>
        <p>Advertising: if you see ads on the site, they come from Google AdSense and are served entirely by Google acting as its own controller for that data. Ads are never shown inside your transcripts or account screens. The voluntary “watch an ad for free credits” feature uses Google's rewarded-ad experience through Google Ad Manager. Google decides the ad content, may use device/usage data to serve it (per Google's own privacy policy), and only then do we credit the minutes. We do not receive your Google profile from this.</p>

        <h3>Deleted data</h3>
        <p>Deleting a job removes its audio and transcript. “Clear history” removes all finished/failed jobs. Deleting your account (write to {CONTACT_EMAIL}) removes your credentials, balances and ledger.</p>

        <h3>Cookies / local storage</h3>
        <p>The site stores your session token in your browser's local storage purely to keep you signed in. We do not use tracking cookies of our own.</p>

        <h3>Contact</h3>
        <p>Questions, data requests or complaints: {CONTACT_EMAIL}. We respond within a week.</p>
      </div>
    </>
  )
}

function Terms() {
  return (
    <>
      <h2>Terms of Service</h2>
      <p className="hint">Last updated: October 2026</p>
      <div className="faq">
        <h3>Using {SITE}</h3>
        <p>{SITE} transcribes audio that you own or have the right to process. You may not upload recordings whose transcription is unlawful, and you confirm you have obtained consent as required by your jurisdiction (and e.g. India's Telegraph Act / DPDP Act) to record and transcribe the calls you upload. Accounts are for one person; bulk automated scraping or resale of the service is not permitted.</p>

        <h3>Credits and payments</h3>
        <p>The service operates on prepaid credit bundles denominated in minutes of audio. Credits are added only after confirmed payment (verified by signature or gateway webhook). A failed transcription never deducts credits. Credits have no cash value and are non-transferable, though they never expire on your account. Because credits are consumed instantly at your request in the ordinary case, the service generally has nothing to refund; genuine billing errors (double-charges, failed jobs that still deducted) will be refunded to your source payment instrument on request at {CONTACT_EMAIL}. Where Indian consumer law grants you additional rights, this clause does not limit them.</p>
        <p>Video/audio quality inputs must conform to the accepted formats and file size limit shown in the uploader. Files that cannot be processed yield no transcript and no charge.</p>

        <h3>Earned free minutes</h3>
        <p>Minutes granted for watching an ad (or as a signup grant) behave like paid credits but hold no cash value. We may withdraw or change reward offers at any time; existing earned credits remain usable.</p>

        <h3>Accuracy disclaimer</h3>
        <p>Transcripts are machine-generated and may contain errors. Information in a transcript is not a certified or notarised record of the audio; legal, business or medical decisions should not be taken on a machine transcript alone. Model agreement highlighting is provided as a guide, not a guarantee.</p>

        <h3>Availability and changes</h3>
        <p>The service depends on third-party AI providers' availability. We may change models, weights, prices or features at any time, and will not be liable for interruptions. You may stop using the service at any time; you keep any remaining credits.</p>

        <h3>Liability</h3>
        <p>To the maximum extent permitted by law, our aggregate liability to you for any claim arising out of the service is limited to the amount you paid us for credits in the 30 days before the claim.</p>

        <h3>Governing law</h3>
        <p>These terms follow the laws of India; disputes are subject to the exclusive jurisdiction of the courts of Tamil Nadu.</p>

        <h3>Recommendations, affiliate links and ads</h3>
        <p>Some outbound links are affiliate links for tools we recommend: if you buy through one, we may earn a commission at no extra cost to you. Every affiliate block is labelled as an advertisement/affiliation next to the links; we only list tools relevant to transcription or improving your recordings, and the recommendation text is ours — the commission never dictates what we show. Rewards for watching ads are governed by the rewarded-ad terms of Google Ad Manager.</p>

        <h3>Contact</h3>
        <p>{CONTACT_EMAIL}</p>
      </div>
    </>
  )
}

export default function Info({ section }) {
  const [cfg, setCfg] = useState(null)
  useEffect(() => { billingConfig().then(setCfg).catch(() => setCfg({})) }, [])
  useEffect(() => { window.scrollTo({ top: 0 }) }, [section])
  return (
    <section className="info-page">
      {section === 'faq' && <Faq />}
      {section === 'privacy' && <Privacy />}
      {section === 'terms' && <Terms />}
      <p className="hint info-foot">
        Questions? Write to {CONTACT_EMAIL}.
        {cfg?.enabled ? ' Free accounts start with free transcription minutes.' : ''}
      </p>
    </section>
  )
}
