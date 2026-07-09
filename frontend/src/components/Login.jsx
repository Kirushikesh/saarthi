import { useEffect, useState } from 'react'
import { api } from '../api'
import Avatar from './Avatar'

const EMOJI = { C001: '👨‍💻', C002: '👩‍💼', C003: '🧔‍♂️', C004: '👩‍🎨', C005: '🌏' }

export default function Login({ onSelect }) {
  const [customers, setCustomers] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    api.customers().then(setCustomers).catch((e) => setErr(e.message))
  }, [])

  return (
    <div className="login">
      <div className="login-hero">
        <Avatar state="idle" size={96} />
        <h1>Saarthi</h1>
        <p className="tagline">IDBI Bank's AI Wealth Companion</p>
        <p className="subtag">Avatar-based · Multilingual · Household-aware advisory</p>
      </div>
      <div className="login-note">Demo: sign in as a synthetic IDBI customer</div>
      {err && <div className="error pad">⚠️ Backend unreachable: {err}</div>}
      {!customers && !err && <div className="muted pad">Loading customers…</div>}
      <div className="persona-grid">
        {customers?.map((c) => (
          <button key={c.id} className="persona" onClick={() => onSelect(c)}>
            <div className="persona-emoji">{EMOJI[c.id] || '🙂'}</div>
            <div className="persona-name">{c.name}</div>
            <div className="persona-sub">{c.occupation}</div>
            <div className="persona-tags">
              <span className="pill">{c.segment}</span>
              <span className="pill">{c.risk_profile}</span>
              {c.joint_account && <span className="pill hs">👫 Joint</span>}
            </div>
          </button>
        ))}
      </div>
      <div className="login-footer">Team FinFusion.AI · IDBI Innovate 2026 · Track 1</div>
    </div>
  )
}
