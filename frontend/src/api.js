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
}

export const inr = (n) => {
  if (n == null) return '—'
  const abs = Math.abs(n)
  if (abs >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`
  if (abs >= 1e5) return `₹${(n / 1e5).toFixed(1)} L`
  return `₹${n.toLocaleString('en-IN')}`
}
