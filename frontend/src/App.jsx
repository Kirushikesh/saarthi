import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { LANGS } from './i18n'
import { speakPlain } from './useSpeech'
import Chat from './components/Chat'
import Dashboard from './components/Dashboard'
import Humsafar from './components/Humsafar'
import Login from './components/Login'
import RMConsole from './components/RMConsole'

const TABS = [
  { id: 'advisor', label: 'Advisor', icon: '💬' },
  { id: 'dashboard', label: 'Portfolio', icon: '📊' },
  { id: 'humsafar', label: 'Humsafar', icon: '👫' },
  { id: 'rm', label: 'RM Console', icon: '🏦' },
]

export default function App() {
  const [customer, setCustomer] = useState(null)
  const [tab, setTab] = useState('advisor')
  const [lang, setLang] = useState('en')
  const [voiceOn, setVoiceOn] = useState(true)
  // Sugam mode = accessibility mode: larger type, higher contrast, bigger
  // touch targets, and the agent replies in simple jargon-free language.
  const [sugam, setSugam] = useState(() => localStorage.getItem('sugam') === '1')
  const [householdMode, setHouseholdMode] = useState(false)
  const [leadFlash, setLeadFlash] = useState(false)
  const [consent, setConsent] = useState(null) // consent status when modal is open
  const [notifs, setNotifs] = useState({ items: [], unread: 0 })
  const [notifOpen, setNotifOpen] = useState(false)
  const [toast, setToast] = useState(null) // newest heartbeat notification, shown briefly
  const seenNotifIds = useRef(null) // null until first poll → no toast on login backlog

  // Poll the proactive-heartbeat feed; toast anything that arrives live.
  useEffect(() => {
    if (!customer) return
    seenNotifIds.current = null
    let timer
    const poll = async () => {
      try {
        const n = await api.notifications(customer.id)
        setNotifs(n)
        const fresh = seenNotifIds.current
          ? n.items.filter((i) => !seenNotifIds.current.has(i.id) && !i.read)
          : []
        seenNotifIds.current = new Set(n.items.map((i) => i.id))
        if (fresh.length > 0) {
          setToast(fresh[0])
          setTimeout(() => setToast(null), 6000)
          // Sugam mode: proactive alerts are spoken, not just shown
          if (localStorage.getItem('sugam') === '1') speakPlain(fresh[0].title)
        }
      } catch { /* backend not up yet */ }
    }
    poll()
    timer = setInterval(poll, 5000)
    return () => clearInterval(timer)
  }, [customer])

  const toggleSugam = () => {
    const next = !sugam
    setSugam(next)
    localStorage.setItem('sugam', next ? '1' : '0')
  }

  const openNotifs = async () => {
    const opening = !notifOpen
    setNotifOpen(opening)
    if (opening && notifs.unread > 0) {
      try { setNotifs(await api.readNotifications(customer.id)) } catch {}
    }
  }

  const toggleHousehold = async () => {
    if (householdMode) { setHouseholdMode(false); return }
    try {
      const s = await api.consent(customer.id)
      if (s.active) setHouseholdMode(true)
      else setConsent(s)
    } catch { setHouseholdMode(true) }
  }

  if (!customer) {
    return (
      <div className="shell">
        <div className={`phone ${sugam ? 'sugam' : ''}`}>
          <Login onSelect={(c) => { setCustomer(c); setHouseholdMode(false); setTab('advisor') }} />
        </div>
        <Sidebar />
      </div>
    )
  }

  return (
    <div className="shell">
      <div className={`phone ${sugam ? 'sugam' : ''}`}>
        <header className="appbar">
          <button className="back" onClick={() => setCustomer(null)} aria-label="Sign out and go back">‹</button>
          <div className="appbar-title">
            <b>Saarthi</b>
            <span className="appbar-sub">IDBI Mobile · {customer.name.split(' ')[0]}</span>
          </div>
          <div className="appbar-actions">
            <button className="toggle bell" onClick={openNotifs} title="Saarthi noticed"
              aria-label={`Notifications, ${notifs.unread} unread`}>
              🔔{notifs.unread > 0 && <span className="bell-badge" aria-hidden="true">{notifs.unread}</span>}
            </button>
            <select className="lang-select" value={lang} onChange={(e) => setLang(e.target.value)} title="Language" aria-label="Language">
              {LANGS.map((l) => <option key={l.code} value={l.code}>{l.native}</option>)}
            </select>
            <button className={`toggle ${sugam ? 'on' : ''}`} onClick={toggleSugam}
              title="Sugam mode — larger text, high contrast, simple language"
              aria-label="Sugam accessibility mode" aria-pressed={sugam}>
              ♿
            </button>
            <button className={`toggle ${voiceOn ? 'on' : ''}`} onClick={() => setVoiceOn(!voiceOn)}
              title="Voice replies" aria-label="Spoken replies" aria-pressed={voiceOn}>
              {voiceOn ? '🔊' : '🔇'}
            </button>
          </div>
        </header>

        {customer.joint_account && (tab === 'advisor' || tab === 'humsafar') && (
          <div className={`hs-banner ${householdMode ? 'active' : ''}`}>
            <span>👫 Humsafar mode {householdMode ? 'ON — advising your household' : 'off'}</span>
            <button onClick={toggleHousehold}>
              {householdMode ? 'Switch to individual' : 'Plan together'}
            </button>
          </div>
        )}

        {toast && !notifOpen && (
          <div className="notif-toast" role="status" onClick={() => { setToast(null); openNotifs() }}>
            <span className="notif-toast-icon" aria-hidden="true">{toast.icon}</span>
            <div>
              <div className="notif-toast-title">{toast.title}</div>
              <div className="notif-toast-sub">Saarthi noticed this for you · tap to view</div>
            </div>
          </div>
        )}

        {notifOpen && (
          <div className="notif-panel">
            <div className="notif-panel-head">
              <b>🫀 Saarthi noticed</b>
              <span className="notif-panel-sub">Proactive heartbeat — Saarthi watches your money even when you don't ask</span>
              <button className="modal-close" onClick={() => setNotifOpen(false)}>Close</button>
            </div>
            {notifs.items.length === 0 && (
              <div className="empty-state small">Nothing yet — Saarthi's next heartbeat will scan your portfolio and today's market.</div>
            )}
            {notifs.items.map((n) => (
              <div key={n.id} className={`notif-row ${n.source === 'rm' ? 'rm' : ''}`}>
                <span className="nudge-icon" aria-hidden="true">{n.icon}</span>
                <div>
                  <div className="nudge-title">{n.title}</div>
                  <div className="nudge-body">{n.body}</div>
                  <div className="notif-meta">{n.source === 'rm' ? 'From your Relationship Manager' : 'Heartbeat insight'} · {n.ts.replace('T', ' ')}</div>
                </div>
                <button className="readaloud" onClick={() => speakPlain(`${n.title}. ${n.body}`, lang)} aria-label="Read this notification aloud" title="Read aloud">🔊</button>
              </div>
            ))}
          </div>
        )}

        {consent && (
          <ConsentModal
            consent={consent}
            customer={customer}
            onClose={() => setConsent(null)}
            onGranted={(s) => {
              setConsent(null)
              if (s.active) setHouseholdMode(true)
            }}
          />
        )}

        <main className="content">
          {tab === 'advisor' && (
            <Chat
              customer={customer}
              householdMode={householdMode}
              lang={lang}
              voiceOn={voiceOn}
              sugam={sugam}
              onLead={() => { setLeadFlash(true); setTimeout(() => setLeadFlash(false), 4000) }}
            />
          )}
          {tab === 'dashboard' && <Dashboard customer={customer} lang={lang} />}
          {tab === 'humsafar' && <Humsafar customer={customer} />}
          {tab === 'rm' && <RMConsole />}
        </main>

        <nav className="tabbar" aria-label="Main sections">
          {TABS.map((t) => (
            <button key={t.id} className={`tab ${tab === t.id ? 'active' : ''} ${t.id === 'rm' && leadFlash ? 'flash' : ''}`}
              onClick={() => setTab(t.id)} aria-current={tab === t.id ? 'page' : undefined}>
              <span className="tab-icon" aria-hidden="true">{t.icon}</span>
              <span>{t.label}</span>
            </button>
          ))}
        </nav>
      </div>
      <Sidebar />
    </div>
  )
}

function ConsentModal({ consent, customer, onClose, onGranted }) {
  const [busy, setBusy] = useState(false)
  const grant = async () => {
    setBusy(true)
    try {
      const s = await api.setConsent(customer.id, true)
      onGranted(s)
    } finally { setBusy(false) }
  }
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-title">👫 Activate Humsafar mode</div>
        <p className="modal-sub">
          Humsafar mode lets Saarthi advise you and <b>{consent.partner_name}</b> as one household.
          Under the DPDP Act, this needs <b>mutual, revocable consent</b> from both of you.
        </p>
        <div className="consent-scope">
          <div className="consent-scope-title">What gets shared between you two</div>
          {consent.shared_scope.map((s) => <div key={s} className="consent-item">✓ {s}</div>)}
        </div>
        <div className={`consent-partner ${consent.partner_granted ? 'ok' : ''}`}>
          {consent.partner_granted
            ? <>✅ {consent.partner_name} consented on {consent.partner_granted_on} (from her IDBI Mobile app)</>
            : <>⏳ Waiting for {consent.partner_name}'s consent — they'll get a notification</>}
        </div>
        <button className="consent-btn" onClick={grant} disabled={busy}>
          {busy ? 'Recording consent…' : 'I consent — activate Humsafar mode'}
        </button>
        <div className="consent-fineprint">
          Consent is logged with a timestamp and can be revoked by either partner at any time.
          Revoking instantly stops all household-level access.
        </div>
        <button className="modal-close" onClick={onClose}>Not now</button>
      </div>
    </div>
  )
}

function Sidebar() {
  return (
    <aside className="sidebar">
      <h2>Saarthi <span className="accent">×</span> IDBI Innovate 2026</h2>
      <p className="side-tag">Track 1 · AI-Powered Digital Wealth Management</p>
      <ul>
        <li><b>🧑‍✈️ Avatar advisor</b> — realtime voice + text in 7 languages (English, हिंदी, தமிழ், తెలుగు, ಕನ್ನಡ, বাংলা, मराठी)</li>
        <li><b>📈 Market pulse</b> — daily index moves translated into "your funds today" impact</li>
        <li><b>🔐 Consent-first households</b> — Humsafar mode activates only on mutual, revocable, audit-logged consent (DPDP-aligned)</li>
        <li><b>📊 360° portfolio</b> — savings, FDs, MFs, NPS, EPF, spends & goals in one view</li>
        <li><b>🎯 Suitability engine</b> — deterministic product scoring (risk band, horizon, buffer, behaviour) with a SEBI-style advice audit trail</li>
        <li><b>🧠 Behavioural analytics</b> — spend categories & behaviour signals derived from raw transaction narrations, not pre-labeled data</li>
        <li><b>🧮 Scenario simulation</b> — "Can I afford it?" answered with EMI + FOIR math</li>
        <li><b>🧭 Life planning</b> — retirement readiness, tax-saving lens & target-SIP planning, all code-computed</li>
        <li><b>🫀 Proactive heartbeat</b> — a background pulse scans every portfolio against today's market and reaches out first: 🔔 alerts arrive unprompted</li>
        <li><b>🛡️ Compliance gate + RM copilot</b> — regulated intents detected in all 7 languages (multilingual patterns + LLM backstop), routed to human RMs as qualified leads with an AI pre-meeting brief the RM just approves</li>
        <li><b>👫 Humsafar mode</b> — India's first household-level advisory: joint net worth, joint goals & an impartial money mediator, with a monthly "State of our Union" report</li>
        <li><b>♿ Sugam mode</b> — banking for every customer: larger text & touch targets, high contrast, spoken alerts, screen-reader support, and the advisor switches to simple jargon-free language (RPwD-Act-aligned)</li>
      </ul>
      <p className="side-note">Synthetic data only · Prototype for IDBI Innovate 2026 · Team FinFusion.AI</p>
    </aside>
  )
}
