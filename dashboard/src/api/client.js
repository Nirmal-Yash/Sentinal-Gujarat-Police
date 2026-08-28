const BASE = import.meta.env.VITE_API_URL || '/api'

async function req(path, opts = {}) {
  const token = localStorage.getItem('sentinel.jwt')
  const isForm = opts.body instanceof FormData
  const res = await fetch(`${BASE}${path}`, {
    headers: { ...(isForm ? {} : { 'Content-Type': 'application/json' }), ...(token ? { Authorization: `Bearer ${token}` } : {}), ...opts.headers },
    ...opts,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export const api = {
  getCameras:      ()            => req('/cameras/'),
  getAuthConfig:   ()            => req('/auth/config'),
  getMe:           ()            => req('/auth/me'),
  login:           (body)        => req('/auth/login', { method: 'POST', body: JSON.stringify(body) }),
  refresh:         ()            => req('/auth/refresh', { method: 'POST' }),
  logout:          ()            => req('/auth/logout', { method: 'POST' }),
  getCameraStats:  ()            => req('/cameras/stats/summary'),
  getPipelineStats:()            => req('/cameras/pipeline/stats'),
  getRecentAnalytics: ()         => req('/cameras/analytics/recent'),
  getAlerts:       (p = {})     => req('/alerts/?' + new URLSearchParams(p)),
  getAlertCounts:  ()            => req('/alerts/stats/counts'),
  ackAlert:        (id, op)      => req(`/alerts/${id}/acknowledge?operator=${op}`, { method: 'POST' }),
  getWatchlist:    ()            => req('/watchlist/'),
  addWatchlist:    (body)        => req('/watchlist/', { method: 'POST', body: JSON.stringify(body) }),
  removeWatchlist: (id)          => req(`/watchlist/${id}`, { method: 'DELETE' }),
  searchCameras:   (q, opts = {}) => req(`/search/cameras?q=${encodeURIComponent(q)}`, opts),
  searchPlate:     (q, opts = {}) => req(`/search/plate?q=${encodeURIComponent(q)}`, opts),
  searchTrack:     (id)          => req(`/search/track/${id}`),
  recentAlerts:    (m, p)        => req(`/search/alerts/recent?minutes=${m}${p ? `&priority=${p}` : ''}`),
  onboardCamera:   (body)        => req('/cameras/onboard', { method: 'POST', body: JSON.stringify(body) }),
  importCameras:   (file)        => { const data = new FormData(); data.append('file', file); return req('/cameras/imports/csv', { method: 'POST', body: data, headers: {} }) },
  getVendors:      ()            => req('/vendors/'),
  createVendor:    (body)        => req('/vendors/', { method: 'POST', body: JSON.stringify(body) }),
  getVendorModels: (id)          => req(`/vendors/${id}/models`),
  createVendorModel: (id, body)  => req(`/vendors/${id}/models`, { method: 'POST', body: JSON.stringify(body) }),
  getTestAssets: ()              => req('/test/assets'),
  uploadTestVideo: (file)        => { const data = new FormData(); data.append('file', file); return req('/test/feeds/upload', { method: 'POST', body: data, headers: {} }) },
  createTestSession: (body)      => req('/test/sessions', { method: 'POST', body: JSON.stringify(body) }),
  getActiveTestSession: ()       => req('/test/sessions/active'),
  getTestStatus: (id)            => req(`/test/sessions/${id}/status`),
  getTestCameras: (id)           => req(`/test/sessions/${id}/cameras`),
  getTestResults: (id, params = {}) => req(`/test/sessions/${id}/results?${new URLSearchParams(params)}`),
  closeTestSession: (id)         => req(`/test/sessions/${id}`, { method: 'DELETE' }),
  downloadTestResults: async (id) => {
    const token = localStorage.getItem('sentinel.jwt'); const res = await fetch(`${BASE}/test/sessions/${id}/results/export`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`); return res.blob()
  },
  downloadDetections: async ()   => {
    const token = localStorage.getItem('sentinel.jwt'); const res = await fetch(`${BASE}/reports/detections?format=csv`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`); return res.blob()
  },
}

export const WS_URL =
  import.meta.env.VITE_WS_URL ||
  `ws://${window.location.host}/ws/alerts`
