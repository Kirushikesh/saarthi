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
  report: (id) => get(`/api/report/${id}`),
  leads: () => get('/api/leads'),
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
