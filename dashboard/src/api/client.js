const BASE = import.meta.env.VITE_API_URL || '/api'

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export const api = {
  getCameras:      ()            => req('/cameras/'),
  getCameraStats:  ()            => req('/cameras/stats/summary'),
  getPipelineStats:()            => req('/cameras/pipeline/stats'),
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
}

export const WS_URL =
  import.meta.env.VITE_WS_URL ||
  `ws://${window.location.host}/ws/alerts`
