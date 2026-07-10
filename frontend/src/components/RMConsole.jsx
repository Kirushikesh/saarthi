import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { api } from '../api'

export default function RMConsole() {
  const [leads, setLeads] = useState([])
  // Per-lead copilot state, kept outside the polled list so refreshes don't wipe it:
  // { [leadId]: { loading, brief, draft, editing, sent, error } }
  const [copilot, setCopilot] = useState({})

  useEffect(() => {
    api.leads().then(setLeads).catch(() => {})
    const t = setInterval(() => api.leads().then(setLeads).catch(() => {}), 4000)
    return () => clearInterval(t)
  }, [])

  const patch = (id, changes) =>
    setCopilot((c) => ({ ...c, [id]: { ...c[id], ...changes } }))

  const prepare = async (lead) => {
    patch(lead.id, { loading: true, error: null })
    try {
      const b = await api.leadBrief(lead.id)
      patch(lead.id, { loading: false, brief: b.brief, draft: b.draft_message })
    } catch (e) {
      patch(lead.id, { loading: false, error: e.message })
    }
  }

  const approve = async (lead) => {
    const cp = copilot[lead.id]
    patch(lead.id, { loading: true })
    try {
      await api.approveLead(lead.id, cp.draft)
      patch(lead.id, { loading: false, sent: true, editing: false })
      api.leads().then(setLeads).catch(() => {})
    } catch (e) {
      patch(lead.id, { loading: false, error: e.message })
    }
  }

  return (
    <div className="dash">
      <div className="card">
        <div className="card-title">🏦 RM Lead Console <span className="pill live">LIVE</span></div>
        <p className="muted small">
          Qualified leads from two engines: the <b>Compliance Gate</b> (regulated intents routed
          to a certified human) and <b>proactive opportunity scans</b> (idle funds, unfundable
          goals — complex cases a seasoned RM should own). For each lead, Saarthi preps the RM
          with a pre-meeting brief and drafts the customer reply — <b>the RM approves, the AI produces</b>.
        </p>
        {leads.length === 0 && (
          <div className="empty-state small">
            No leads yet. Ask Saarthi about <i>term insurance</i> or <i>PMS</i> as a customer — the compliance gate will route it here.
          </div>
        )}
        {leads.map((l) => {
          const cp = copilot[l.id] || {}
          const sent = cp.sent || l.status === 'RM MESSAGE SENT'
          return (
            <div key={l.id} className={`lead-row ${l.priority === 'HIGH' ? 'high' : ''}`}>
              <div className="lead-row-head">
                <b>{l.customer_name}</b>
                <span className={`pill kind-${l.kind || 'compliance'}`}>
                  {l.kind === 'opportunity' ? '💡 Opportunity' : '🛡️ Compliance'}
                </span>
                <span className={`pill ${l.priority === 'HIGH' ? 'hot' : ''}`}>{l.priority}</span>
              </div>
              <div className="lead-product">{l.product}{l.household ? ' · household query' : ''}</div>
              <div className="lead-context">{l.context}</div>
              <div className="lead-meta">{l.id} · {l.segment} · {l.created} · {sent ? 'RM MESSAGE SENT ✓' : l.status}</div>

              {!cp.brief && (
                <button className="brief-btn" onClick={() => prepare(l)} disabled={cp.loading}>
                  {cp.loading ? 'Saarthi is preparing…' : '✨ Prepare with Saarthi'}
                </button>
              )}
              {cp.error && <div className="error">{cp.error}</div>}

              {cp.brief && (
                <>
                  <div className="brief-box">
                    <div className="brief-label">📋 Pre-meeting brief</div>
                    <div className="report-body"><ReactMarkdown>{cp.brief}</ReactMarkdown></div>
                  </div>
                  <div className="brief-box draft">
                    <div className="brief-label">💬 Drafted reply to {l.customer_name.split(' ')[0]}</div>
                    {cp.editing ? (
                      <textarea
                        className="draft-edit"
                        value={cp.draft}
                        onChange={(e) => patch(l.id, { draft: e.target.value })}
                        rows={4}
                      />
                    ) : (
                      <p className="draft-text">{cp.draft}</p>
                    )}
                    {sent ? (
                      <div className="draft-sent">✅ Sent — delivered to the customer's Saarthi notifications</div>
                    ) : (
                      <div className="draft-actions">
                        <button className="approve-btn" onClick={() => approve(l)} disabled={cp.loading}>
                          {cp.loading ? 'Sending…' : '✅ Approve & Send'}
                        </button>
                        <button className="edit-btn" onClick={() => patch(l.id, { editing: !cp.editing })}>
                          {cp.editing ? 'Done editing' : '✏️ Edit'}
                        </button>
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
