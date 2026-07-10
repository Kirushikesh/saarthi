import { useEffect, useState } from 'react'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { api, inr } from '../api'
import { speakPlain } from '../useSpeech'

const COLORS = ['#0d9488', '#f59e0b', '#0369a1', '#7c3aed', '#e11d48']

// Read-aloud with speech-friendly Indian notation (₹12.5 L → "rupees 12.5 lakh")
const say = (text, lang) =>
  speakPlain(text.replaceAll('₹', 'rupees ').replace(/\bCr\b/g, 'crore').replace(/\bL\b/g, 'lakh'), lang)

function MarketPulse({ market }) {
  const pi = market.portfolio_impact
  const up = pi && pi.day_change_inr >= 0
  return (
    <div className="card">
      <div className="card-title">Market Pulse <span className="pill">{market.as_of}</span></div>
      <div className="ticker-row">
        {market.indices.map((ix) => (
          <div key={ix.name} className="ticker">
            <div className="ticker-name">{ix.name}</div>
            <div className={`ticker-chg ${ix.chg_1d_pct >= 0 ? 'gain' : 'loss'}`}>
              {ix.chg_1d_pct >= 0 ? '▲' : '▼'} {Math.abs(ix.chg_1d_pct)}%
            </div>
          </div>
        ))}
      </div>
      {pi && (
        <div className={`impact-strip ${up ? 'up' : 'down'}`}>
          <b>Your funds today: {up ? '+' : '−'}{inr(Math.abs(pi.day_change_inr))} ({pi.day_change_pct >= 0 ? '+' : ''}{pi.day_change_pct}%)</b>
          <span>{pi.note}</span>
        </div>
      )}
    </div>
  )
}

function HealthGauge({ health, lang }) {
  const R = 52, C = Math.PI * R // semicircle circumference
  const color = health.score >= 80 ? '#16a34a' : health.score >= 60 ? '#0d9488' : health.score >= 40 ? '#f59e0b' : '#e11d48'
  return (
    <div className="card">
      <div className="card-title">Financial Health Score
        <button className="readaloud" title="Read aloud" aria-label="Read your health score aloud"
          onClick={() => say(`Your financial health score is ${health.score} out of 100 — ${health.grade}.`, lang)}>🔊</button>
      </div>
      <div className="health-row">
        <svg width="130" height="76" viewBox="0 0 130 76" role="img"
          aria-label={`Financial health score ${health.score} out of 100, ${health.grade}`}>
          <path d="M 13 68 A 52 52 0 0 1 117 68" fill="none" stroke="#e2e8f0" strokeWidth="11" strokeLinecap="round" />
          <path d="M 13 68 A 52 52 0 0 1 117 68" fill="none" stroke={color} strokeWidth="11" strokeLinecap="round"
            strokeDasharray={`${(health.score / 100) * C} ${C}`} />
          <text x="65" y="58" textAnchor="middle" fontSize="24" fontWeight="800" fill={color}>{health.score}</text>
          <text x="65" y="72" textAnchor="middle" fontSize="10" fill="#64748b">{health.grade}</text>
        </svg>
        <div className="health-pillars">
          {health.pillars.map((pl) => (
            <div key={pl.name} className="pillar" title={pl.detail}>
              <div className="pillar-head"><span>{pl.name}</span><b>{pl.score}/{pl.max}</b></div>
              <div className="pillar-bar"><div style={{ width: `${(pl.score / pl.max) * 100}%` }} /></div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function BehaviorCard({ behavior }) {
  return (
    <div className="card">
      <div className="card-title">Behavioural Profile <span className="pill">{behavior.behavioral_segment}</span></div>
      {behavior.signals.map((s) => (
        <div key={s} className="behavior-signal">• {s}</div>
      ))}
      <div className="derived-note">
        Derived from {behavior.derived_from} · classifier coverage {behavior.classifier_coverage.coverage_pct}%
      </div>
    </div>
  )
}

// Account Aggregator: the "holdings at other institutions" ask — external
// accounts join the 360° only under purpose-bound, revocable AA consent.
function AACard({ aa, external, onLink, onUnlink, busy }) {
  if (aa.linked && external) {
    return (
      <div className="card">
        <div className="card-title">🔗 Other Institutions <span className="pill live">via Account Aggregator</span></div>
        {external.accounts.map((a) => (
          <div key={a.fip + a.type} className="holding">
            <div>
              <div className="h-name">{a.fip}</div>
              <div className="h-sub">{a.type} · {a.detail}</div>
            </div>
            <div className="h-right">
              <div className="h-val">{inr(a.value)}</div>
              <div className="h-sub">{a.market_linked ? 'market-linked' : 'deposit/cash'}</div>
            </div>
          </div>
        ))}
        <div className="aa-consent-line">
          🔐 Fetched under AA consent ({aa.consent.purpose}) · valid till {aa.consent.valid_till} · revocable anytime
          <button className="consent-revoke" onClick={onUnlink} disabled={busy}>Revoke</button>
        </div>
      </div>
    )
  }
  return (
    <div className="card aa-cta">
      <div className="card-title">🔗 Complete your 360° view</div>
      <p className="muted small">
        You hold accounts at <b>{aa.discovered.join(', ')}</b>. Link them through the RBI's
        Account Aggregator framework — consent-based, purpose-bound, revocable — and Saarthi
        will advise on your <b>full</b> financial picture, not just your IDBI holdings.
      </p>
      <button className="report-btn" onClick={onLink} disabled={busy}>
        {busy ? 'Fetching via AA…' : '🔗 Link via Account Aggregator'}
      </button>
    </div>
  )
}

function AuditTrailCard({ trail }) {
  return (
    <div className="card">
      <div className="card-title">📜 Advice Audit Trail <span className="pill">SEBI-style record</span></div>
      <p className="muted small">Every product Saarthi assesses for you is scored by a deterministic suitability engine and logged — the "why" behind each recommendation.</p>
      {trail.length === 0 && (
        <div className="empty-state small">No assessments yet — ask Saarthi to recommend an investment.</div>
      )}
      {trail.slice(0, 6).map((e, i) => (
        <div key={i} className="audit-row">
          <div className="audit-head">
            <b>{e.product}</b>
            <span className={`pill verdict-${e.verdict.toLowerCase()}`}>{e.verdict.replaceAll('_', ' ')}</span>
          </div>
          <div className="audit-reasons">{e.reasons.slice(0, 2).join(' · ')}</div>
          <div className="audit-meta">{e.ts.replace('T', ' ')} · via {e.via === 'agent_tool' ? 'Saarthi advisory' : 'API'}</div>
        </div>
      ))}
    </div>
  )
}

export default function Dashboard({ customer, lang }) {
  const [p, setP] = useState(null)
  const [nudges, setNudges] = useState([])
  const [health, setHealth] = useState(null)
  const [market, setMarket] = useState(null)
  const [behavior, setBehavior] = useState(null)
  const [trail, setTrail] = useState(null)
  const [aa, setAA] = useState(null)
  const [aaBusy, setAABusy] = useState(false)
  const [err, setErr] = useState(null)

  const refresh = () => {
    Promise.all([api.portfolio(customer.id), api.nudges(customer.id), api.healthScore(customer.id), api.market(customer.id)])
      .then(([pf, nd, hs, mk]) => { setP(pf); setNudges(nd); setHealth(hs); setMarket(mk) })
      .catch((e) => setErr(e.message))
    api.aa(customer.id).then(setAA).catch(() => {})
  }

  useEffect(() => {
    setP(null)
    refresh()
    api.behavior(customer.id).then(setBehavior).catch(() => {})
    api.suitability(customer.id).then((s) => setTrail(s.audit_trail)).catch(() => {})
  }, [customer.id]) // eslint-disable-line

  const setAALink = async (link) => {
    setAABusy(true)
    try { await api.aaLink(customer.id, link); refresh() } finally { setAABusy(false) }
  }

  if (err) return <div className="pad error">⚠️ {err}</div>
  if (!p) return <div className="pad muted">Loading portfolio…</div>

  const alloc = Object.entries(p.allocation).filter(([, v]) => v > 0).map(([name, value]) => ({ name, value }))
  const spend = Object.entries(p.spend_by_category).slice(0, 6)
  const maxSpend = Math.max(...spend.map(([, v]) => v), 1)

  return (
    <div className="dash">
      <div className="networth-card">
        <div className="nw-label">Net Worth
          <button className="readaloud light" title="Read aloud" aria-label="Read your net worth aloud"
            onClick={() => say(`Your net worth is ${inr(p.net_worth)}. Assets ${inr(p.total_assets)}, liabilities ${inr(p.total_liabilities)}, monthly SIP ${inr(p.monthly_sip)}.`, lang)}>🔊</button>
        </div>
        <div className="nw-value">{inr(p.net_worth)}</div>
        <div className="nw-sub">
          Assets {inr(p.total_assets)} · Liabilities {inr(p.total_liabilities)} · SIP {inr(p.monthly_sip)}/mo
          {p.external && <> · incl. {inr(p.external.total)} at other institutions 🔗</>}
        </div>
      </div>

      {aa?.available && (
        <AACard aa={aa} external={p.external} busy={aaBusy}
          onLink={() => setAALink(true)} onUnlink={() => setAALink(false)} />
      )}

      {market && <MarketPulse market={market} />}

      {health && <HealthGauge health={health} lang={lang} />}

      {behavior && <BehaviorCard behavior={behavior} />}

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

      {trail && <AuditTrailCard trail={trail} />}

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
