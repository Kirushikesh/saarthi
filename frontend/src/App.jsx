import { useState } from 'react'
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
            <button className={`toggle ${lang === 'hi' ? 'on' : ''}`} onClick={() => setLang(lang === 'en' ? 'hi' : 'en')} title="Language">
              {lang === 'en' ? 'EN' : 'हि'}
            </button>
            <button className={`toggle ${voiceOn ? 'on' : ''}`} onClick={() => setVoiceOn(!voiceOn)} title="Voice replies">
              {voiceOn ? '🔊' : '🔇'}
            </button>
          </div>
        </header>

        {customer.joint_account && (tab === 'advisor' || tab === 'humsafar') && (
          <div className={`hs-banner ${householdMode ? 'active' : ''}`}>
            <span>👫 Humsafar mode {householdMode ? 'ON — advising your household' : 'off'}</span>
            <button onClick={() => setHouseholdMode(!householdMode)}>
              {householdMode ? 'Switch to individual' : 'Plan together'}
            </button>
          </div>
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

function Sidebar() {
  return (
    <aside className="sidebar">
      <h2>Saarthi <span className="accent">×</span> IDBI Innovate 2026</h2>
      <p className="side-tag">Track 1 · AI-Powered Digital Wealth Management</p>
      <ul>
        <li><b>🧑‍✈️ Avatar advisor</b> — voice + text, English & हिन्दी</li>
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
