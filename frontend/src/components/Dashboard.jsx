import { useEffect, useState } from 'react'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { api, inr } from '../api'

const COLORS = ['#0d9488', '#f59e0b', '#0369a1', '#7c3aed', '#e11d48']

export default function Dashboard({ customer }) {
  const [p, setP] = useState(null)
  const [nudges, setNudges] = useState([])
  const [err, setErr] = useState(null)

  useEffect(() => {
    setP(null)
    Promise.all([api.portfolio(customer.id), api.nudges(customer.id)])
      .then(([pf, nd]) => { setP(pf); setNudges(nd) })
      .catch((e) => setErr(e.message))
  }, [customer.id])

  if (err) return <div className="pad error">⚠️ {err}</div>
  if (!p) return <div className="pad muted">Loading portfolio…</div>

  const alloc = Object.entries(p.allocation).filter(([, v]) => v > 0).map(([name, value]) => ({ name, value }))
  const spend = Object.entries(p.spend_by_category).slice(0, 6)
  const maxSpend = Math.max(...spend.map(([, v]) => v), 1)

  return (
    <div className="dash">
      <div className="networth-card">
        <div className="nw-label">Net Worth</div>
        <div className="nw-value">{inr(p.net_worth)}</div>
        <div className="nw-sub">
          Assets {inr(p.total_assets)} · Liabilities {inr(p.total_liabilities)} · SIP {inr(p.monthly_sip)}/mo
        </div>
      </div>

      <div className="card">
        <div className="card-title">Asset Allocation</div>
        <div className="alloc-row">
          <ResponsiveContainer width={130} height={130}>
            <PieChart>
              <Pie data={alloc} dataKey="value" innerRadius={38} outerRadius={60} paddingAngle={2}>
                {alloc.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip formatter={(v) => inr(v)} />
            </PieChart>
          </ResponsiveContainer>
          <div className="alloc-legend">
            {alloc.map((a, i) => (
              <div key={a.name} className="legend-item">
                <span className="dot" style={{ background: COLORS[i % COLORS.length] }} />
                <span>{a.name}</span>
                <b>{inr(a.value)}</b>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-title">Mutual Fund Holdings <span className="pill">{p.mf_current >= p.mf_invested ? '▲' : '▼'} {(((p.mf_current - p.mf_invested) / p.mf_invested) * 100).toFixed(1)}%</span></div>
        {p.holdings.map((h) => (
          <div key={h.name} className="holding">
            <div>
              <div className="h-name">{h.name}</div>
              <div className="h-sub">{h.asset_class} · SIP {inr(h.sip_monthly)}/mo</div>
            </div>
            <div className="h-right">
              <div className="h-val">{inr(h.current)}</div>
              <div className={h.returns_pct >= 0 ? 'gain' : 'loss'}>{h.returns_pct >= 0 ? '+' : ''}{h.returns_pct}%</div>
            </div>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="card-title">Monthly Spending</div>
        {spend.map(([cat, v]) => (
          <div key={cat} className="spend-row">
            <span className="spend-cat">{cat}</span>
            <div className="spend-bar"><div style={{ width: `${(v / maxSpend) * 100}%` }} /></div>
            <span className="spend-val">{inr(v)}</span>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="card-title">Goals</div>
        {p.goals.map((g) => {
          const pct = Math.min(100, Math.round((g.saved / g.target) * 100))
          return (
            <div key={g.name} className="goal">
              <div className="goal-head">
                <span>{g.joint ? '👫 ' : '🎯 '}{g.name}</span>
                <b>{pct}%</b>
              </div>
              <div className="progress"><div style={{ width: `${pct}%` }} /></div>
              <div className="goal-sub">{inr(g.saved)} of {inr(g.target)} · by {g.by}</div>
            </div>
          )
        })}
      </div>

      {nudges.length > 0 && (
        <div className="card">
          <div className="card-title">Saarthi Insights</div>
          {nudges.map((n, i) => (
            <div key={i} className="nudge">
              <span className="nudge-icon">{n.icon}</span>
              <div>
                <div className="nudge-title">{n.title}</div>
                <div className="nudge-body">{n.body}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
