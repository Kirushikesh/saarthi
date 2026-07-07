import { useState } from 'react'
import { api } from './api'
import { LANGS } from './i18n'
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
  const [householdMode, setHouseholdMode] = useState(false)
  const [leadFlash, setLeadFlash] = useState(false)
  const [consent, setConsent] = useState(null) // consent status when modal is open

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
        <div className="phone">
          <Login onSelect={(c) => { setCustomer(c); setHouseholdMode(false); setTab('advisor') }} />
        </div>
        <Sidebar />
      </div>
    )
  }

  return (
    <div className="shell">
      <div className="phone">
        <header className="appbar">
          <button className="back" onClick={() => setCustomer(null)}>‹</button>
          <div className="appbar-title">
            <b>Saarthi</b>
            <span className="appbar-sub">IDBI Mobile · {customer.name.split(' ')[0]}</span>
          </div>
          <div className="appbar-actions">
            <select className="lang-select" value={lang} onChange={(e) => setLang(e.target.value)} title="Language">
              {LANGS.map((l) => <option key={l.code} value={l.code}>{l.native}</option>)}
            </select>
            <button className={`toggle ${voiceOn ? 'on' : ''}`} onClick={() => setVoiceOn(!voiceOn)} title="Voice replies">
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
              onLead={() => { setLeadFlash(true); setTimeout(() => setLeadFlash(false), 4000) }}
            />
          )}
          {tab === 'dashboard' && <Dashboard customer={customer} />}
          {tab === 'humsafar' && <Humsafar customer={customer} />}
          {tab === 'rm' && <RMConsole />}
        </main>

        <nav className="tabbar">
          {TABS.map((t) => (
            <button key={t.id} className={`tab ${tab === t.id ? 'active' : ''} ${t.id === 'rm' && leadFlash ? 'flash' : ''}`} onClick={() => setTab(t.id)}>
              <span className="tab-icon">{t.icon}</span>
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
        <li><b>🎯 Suitability engine</b> — age, risk profile & segment-aware recommendations</li>
        <li><b>🧮 Scenario simulation</b> — "Can I afford it?" answered with EMI + FOIR math</li>
        <li><b>🧭 Life planning</b> — retirement readiness, tax-saving lens & target-SIP planning, all code-computed</li>
        <li><b>🛡️ Compliance gate</b> — regulated products auto-route to human RMs as qualified leads (SEBI/IRDAI-aware hybrid model)</li>
        <li><b>👫 Humsafar mode</b> — India's first household-level advisory: joint net worth, joint goals & an impartial money mediator, with a monthly "State of our Union" report</li>
      </ul>
      <p className="side-note">Synthetic data only · Prototype for IDBI Innovate 2026 · Team FinFusion.AI</p>
    </aside>
  )
}
