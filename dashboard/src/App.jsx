import { useState, useEffect, useCallback, useRef } from 'react'
import { api, WS_URL } from './api/client'
import { useWebSocket } from './hooks/useWebSocket'
import Navbar         from './components/Navbar'
import CameraGrid     from './components/CameraGrid'
import AlertPanel     from './components/AlertPanel'
import MapView        from './components/MapView'
import SearchModal    from './components/SearchModal'
import WatchlistModal from './components/WatchlistModal'

const MAX_LIVE_ALERTS = 300

// ─── SVG view toggle icons ────────────────────────────────────────────────────
const GridViewIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
    <rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>
  </svg>
)

const MapViewIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/>
    <line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/>
  </svg>
)

export default function App() {
  const [cameras,       setCameras]       = useState([])
  const [alerts,        setAlerts]        = useState([])
  const [counts,        setCounts]        = useState(null)
  const [pipelineStats, setPipelineStats] = useState(null)
  const [view,          setView]          = useState('grid')
  const [showSearch,    setShowSearch]    = useState(false)
  const [showWatchlist, setShowWatchlist] = useState(false)

  // Alerts indexed by cam_id for fast badge lookup
  const alertsByCam = (alerts || []).reduce((acc, a) => {
    if (a.cam_id && !a.acknowledged) acc[a.cam_id] = (acc[a.cam_id] || 0) + 1
    return acc
  }, {})

  // ── Initial load ─────────────────────────────────────────────────────────
  useEffect(() => {
    api.getCameras().then(setCameras).catch(console.warn)
    api.getAlertCounts().then(setCounts).catch(console.warn)
    api.getAlerts({ limit: 80 }).then(rows =>
      setAlerts(rows.map(r => ({ ...r, _new: false })))
    ).catch(console.warn)
  }, [])

  // ── Periodic refresh ──────────────────────────────────────────────────────
  useEffect(() => {
    const t = setInterval(() => {
      api.getAlertCounts().then(setCounts).catch(console.warn)
      // Refresh pipeline stats every 10 s to show ingestion/AI health
      fetch('/api/cameras/pipeline/stats')
        .then(r => r.json()).then(setPipelineStats).catch(console.warn)
      // Refresh camera list every 60 s (catalogue sync may add cameras)
      api.getCameras().then(setCameras).catch(console.warn)
    }, 10_000)
    return () => clearInterval(t)
  }, [])

  // ── WebSocket — real-time alerts ──────────────────────────────────────────
  const onMessage = useCallback((msg) => {
    if (msg.type !== 'alert') return
    setAlerts(prev => {
      const next = [{ ...msg, _new: true }, ...prev].slice(0, MAX_LIVE_ALERTS)
      setTimeout(() =>
        setAlerts(a => a.map(x =>
          (x.alert_id === msg.alert_id) ? { ...x, _new: false } : x
        )), 3000)
      return next
    })
    setCounts(c => c ? {
      ...c,
      total:            (c.total || 0) + 1,
      unacknowledged:   (c.unacknowledged || 0) + 1,
      [msg.priority?.toLowerCase()]: (c[msg.priority?.toLowerCase()] || 0) + 1,
    } : c)
  }, [])

  useWebSocket(WS_URL, onMessage)

  // ── Acknowledge ───────────────────────────────────────────────────────────
  const ack = useCallback(async (id) => {
    try {
      await api.ackAlert(id, 'operator')
      setAlerts(a => a.map(x =>
        (x.alert_id === id || x.id === id) ? { ...x, acknowledged: true } : x
      ))
      setCounts(c => c ? { ...c, unacknowledged: Math.max(0, (c.unacknowledged || 1) - 1) } : c)
    } catch (e) { console.warn('ack failed:', e) }
  }, [])

  const unackedCount = counts?.unacknowledged || 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      <Navbar
        alertCount={unackedCount}
        onSearchOpen={() => setShowSearch(true)}
        onWatchlistOpen={() => setShowWatchlist(true)}
      />

      {/* Toolbar: view toggle + status bar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '6px 14px', background: 'var(--surface)',
        borderBottom: '1px solid var(--border)', flexShrink: 0,
      }}>
        {/* View toggle */}
        <div style={{ display: 'flex', gap: 2, background: 'var(--surface2)', borderRadius: 6, padding: 2 }}>
          {[
            ['grid', 'Camera Grid', GridViewIcon],
            ['map',  'Map View',    MapViewIcon ],
          ].map(([v, label, Icon]) => (
            <button key={v} onClick={() => setView(v)} style={{
              display: 'flex', alignItems: 'center', gap: 5,
              padding: '4px 12px', borderRadius: 4, border: 'none', fontSize: 11,
              background: view === v ? 'var(--surface)' : 'transparent',
              color: view === v ? 'var(--text)' : 'var(--text2)',
              cursor: 'pointer', fontWeight: view === v ? 600 : 400,
              boxShadow: view === v ? '0 1px 3px rgba(0,0,0,.3)' : 'none',
              transition: 'all .15s',
            }}>
              <Icon/> {label}
            </button>
          ))}
        </div>

        {/* Status indicators */}
        <div style={{ marginLeft: 8, display: 'flex', gap: 14, fontSize: 11 }}>
          <span style={{ color: 'var(--text2)' }}>
            {cameras.length} cameras
          </span>
          <span style={{ color: 'var(--high)', fontWeight: counts?.high ? 700 : 400 }}>
            {counts?.high || 0} HIGH
          </span>
          <span style={{ color: 'var(--medium)' }}>
            {counts?.medium || 0} MED
          </span>
          <span style={{ color: 'var(--low)' }}>
            {counts?.low || 0} LOW
          </span>
        </div>

        <div style={{ flex: 1 }}/>

        {/* Pipeline health pill */}
        {pipelineStats && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 10,
            background: 'var(--surface2)', borderRadius: 6, padding: '3px 10px',
            border: '1px solid var(--border)', fontSize: 10, color: 'var(--text2)',
          }}>
            <span>Pipeline</span>
            {[
              ['Frames',   pipelineStats.raw_frames,  'var(--green)' ],
              ['Detect',   pipelineStats.detections,  'var(--accent)'],
            ].map(([l, v, c]) => (
              <span key={l} style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                <span style={{ opacity: .6 }}>{l}</span>
                <span style={{ fontWeight: 700, color: c, fontVariantNumeric: 'tabular-nums' }}>
                  {(v || 0).toLocaleString()}
                </span>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Main layout */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Left: camera grid or map */}
        <div style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
          {view === 'grid'
            ? <CameraGrid
                cameras={cameras}
                alertsByCam={alertsByCam}
                pipelineStats={pipelineStats}
              />
            : <MapView cameras={cameras} alerts={alerts}/>
          }
        </div>

        {/* Right: alert panel (fixed 320px) */}
        <div style={{ width: 320, flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <AlertPanel alerts={alerts} onAck={ack} counts={counts}/>
        </div>
      </div>

      {showSearch    && <SearchModal    onClose={() => setShowSearch(false)}/>}
      {showWatchlist && <WatchlistModal onClose={() => setShowWatchlist(false)}/>}
    </div>
  )
}
