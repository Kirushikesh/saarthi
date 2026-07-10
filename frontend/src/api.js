const BASE = import.meta.env.VITE_API_URL || ''

async function get(path) {
  const r = await fetch(`${BASE}${path}`)
  if (!r.ok) throw new Error((await r.json()).detail || r.statusText)
  return r.json()
}

export const api = {
  customers: () => get('/api/customers'),
  portfolio: (id) => get(`/api/portfolio/${id}`),
  household: (id) => get(`/api/household/${id}`),
  nudges: (id) => get(`/api/nudges/${id}`),
  healthScore: (id) => get(`/api/health-score/${id}`),
  behavior: (id) => get(`/api/behavior/${id}`),
  suitability: (id) => get(`/api/suitability/${id}`),
  market: (id) => get(`/api/market/${id}`),
  consent: (id) => get(`/api/consent/${id}`),
  setConsent: async (id, grant) => {
    const r = await fetch(`${BASE}/api/consent/${id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ grant }),
    })
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText)
    return r.json()
  },
  report: (id) => get(`/api/report/${id}`),
  leads: () => get('/api/leads'),
  notifications: (id) => get(`/api/notifications/${id}`),
  readNotifications: async (id) => {
    const r = await fetch(`${BASE}/api/notifications/${id}/read`, { method: 'POST' })
    if (!r.ok) throw new Error(r.statusText)
    return r.json()
  },
  leadBrief: (leadId) => get(`/api/leads/${leadId}/brief`),
  approveLead: async (leadId, message) => {
    const r = await fetch(`${BASE}/api/leads/${leadId}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    })
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText)
    return r.json()
  },
  chat: async (body) => {
    const r = await fetch(`${BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText)
    return r.json()
  },
  aa: (id) => get(`/api/aa/${id}`),
  aaLink: async (id, link) => {
    const r = await fetch(`${BASE}/api/aa/${id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ link }),
    })
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText)
    return r.json()
  },
  // Streaming chat (SSE over fetch): onEvent receives {type: 'status'|'token'|'done'|'error', ...}.
  // Returns the final 'done' payload (same shape as api.chat's response).
  chatStream: async (body, onEvent) => {
    const r = await fetch(`${BASE}/api/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!r.ok || !r.body) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText)
    const reader = r.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    let done = null
    for (;;) {
      const { value, done: eof } = await reader.read()
      if (eof) break
      buf += decoder.decode(value, { stream: true })
      let idx
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const frame = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        const line = frame.split('\n').find((l) => l.startsWith('data: '))
        if (!line) continue
        const ev = JSON.parse(line.slice(6))
        if (ev.type === 'error') throw new Error(ev.message)
        if (ev.type === 'done') done = ev
        onEvent?.(ev)
      }
    }
    if (!done) throw new Error('stream ended unexpectedly')
    return done
  },
}

export const inr = (n) => {
  if (n == null) return '—'
  const abs = Math.abs(n)
  if (abs >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`
  if (abs >= 1e5) return `₹${(n / 1e5).toFixed(1)} L`
  return `₹${n.toLocaleString('en-IN')}`
}
