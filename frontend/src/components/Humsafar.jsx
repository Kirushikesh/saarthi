import { useEffect, useState } from 'react'
import { api, inr } from '../api'

export default function Humsafar({ customer }) {
  const [h, setH] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    setH(null); setErr(null)
    api.household(customer.id).then(setH).catch((e) => setErr(e.message))
  }, [customer.id])

  if (err) return (
    <div className="pad">
      <div className="card empty-state">
        <div style={{ fontSize: 34 }}>👫</div>
        <b>No linked partner yet</b>
        <p className="muted">Humsafar mode unlocks when both partners link their IDBI accounts with mutual consent — unified net worth, joint goals and an impartial AI mediator for money decisions.</p>
      </div>
    </div>
  )
  if (!h) return <div className="pad muted">Loading household…</div>

  const surplus = h.combined_income - h.combined_expenses - h.combined_sip

  return (
    <div className="dash">
      <div className="networth-card humsafar-grad">
        <div className="nw-label">👫 Household Net Worth</div>
        <div className="nw-value">{inr(h.net_worth)}</div>
        <div className="nw-sub">{h.members.map((m) => m.name.split(' ')[0]).join(' + ')} · combined income {inr(h.combined_income)}/mo</div>
      </div>

      <div className="card">
        <div className="card-title">Monthly Cash Flow (combined)</div>
        <div className="cash-row"><span>Income</span><b className="gain">+{inr(h.combined_income)}</b></div>
        <div className="cash-row"><span>Expenses</span><b className="loss">−{inr(h.combined_expenses)}</b></div>
        <div className="cash-row"><span>SIP investments</span><b>−{inr(h.combined_sip)}</b></div>
        <div className="cash-row total"><span>Free surplus</span><b>{inr(surplus)}</b></div>
      </div>

      <div className="card">
        <div className="card-title">Who brings what</div>
        {Object.values(h.individual).map((p) => (
          <div key={p.customer.id} className="member-row">
            <div>
              <div className="h-name">{p.customer.name}</div>
              <div className="h-sub">{p.customer.risk_profile} · income {inr(p.customer.monthly_income)}/mo</div>
            </div>
            <div className="h-right">
              <div className="h-val">{inr(p.net_worth)}</div>
              <div className="h-sub">net worth</div>
            </div>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="card-title">Joint Goals</div>
        {h.joint_goals.map((g) => {
          const pct = Math.min(100, Math.round((g.saved / g.target) * 100))
          return (
            <div key={g.name} className="goal">
              <div className="goal-head"><span>👫 {g.name}</span><b>{pct}%</b></div>
              <div className="progress humsafar"><div style={{ width: `${pct}%` }} /></div>
              <div className="goal-sub">{inr(g.saved)} of {inr(g.target)} · by {g.by}</div>
            </div>
          )
        })}
        <div className="mediator-hint">
          💬 Ask Saarthi in Humsafar mode: <i>"How should we split savings for our home goal?"</i> — the Mediator suggests income-proportional plans that feel fair to both.
        </div>
      </div>
    </div>
  )
}
