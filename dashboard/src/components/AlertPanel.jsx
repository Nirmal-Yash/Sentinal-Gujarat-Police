import { useState } from 'react'
import { api } from '../api/client'

// ─── Priority config (no emojis) ─────────────────────────────────────────────
const PRIO = {
  HIGH:   { color: 'var(--high)',   bg: 'rgba(248,81,73,.10)',   label: 'HIGH'   },
  MEDIUM: { color: 'var(--medium)', bg: 'rgba(210,153,34,.10)',  label: 'MED'    },
  LOW:    { color: 'var(--low)',     bg: 'rgba(63,185,80,.10)',   label: 'LOW'    },
}

const TYPE_LABEL = {
  watchlist_match:         'Watchlist Match',
  cross_camera_sighting:   'Cross-Camera',
  anomaly_running_crowd:   'Running / Crowd',
  anomaly_crowd_formation: 'Crowd Detected',
  anomaly_abandoned_object:'Abandoned Object',
}

const BellIcon = ({ muted = false }) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
    <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
    {muted && <path d="m4 4 16 16"/>}
  </svg>
)

// ─── Type badge indicator bar ─────────────────────────────────────────────────
const TypeBadge = ({ type }) => {
  const colors = {
    watchlist_match:       '#f85149',
    cross_camera_sighting: '#58a6ff',
    anomaly_running_crowd: '#d29922',
    anomaly_crowd_formation:'#d29922',
    anomaly_abandoned_object:'#e3702a',
  }
  return (
    <div style={{
      width: 3, borderRadius: 2, flexShrink: 0, alignSelf: 'stretch',
      background: colors[type] || 'var(--border)',
    }}/>
  )
}

// ─── Alert row ────────────────────────────────────────────────────────────────
function AlertRow({ alert, onAck, onOpenSearch }) {
  const prio = PRIO[alert.priority] || PRIO.MEDIUM
  const ageMs = Date.now() - new Date(alert.created_at || (parseFloat(alert.timestamp || 0) * 1000)).getTime()
  const escalated = !alert.acknowledged && Number.isFinite(ageMs) && ageMs > 5 * 60 * 1000
  const ts   = (() => {
    try {
      const d = alert.timestamp
        ? new Date(parseFloat(alert.timestamp) * 1000)
        : new Date(alert.created_at)
      return d.toLocaleTimeString('en-IN', { hour:'2-digit', minute:'2-digit', second:'2-digit', hour12: false })
    } catch { return '—' }
  })()

  const subtitle = alert.details?.watchlist_name
    || alert.details?.message
    || alert.details?.anomaly_type?.replace(/_/g, ' ')
    || alert.details?.description
    || (alert.cam_id ? `Cam ${alert.cam_id.slice(0, 8)}` : null)
    || '—'

  return (
    <div style={{
      display: 'flex', gap: 8, padding: '8px 12px',
      borderBottom: '1px solid var(--border)',
      background: alert._new ? 'rgba(88,166,255,.04)' : 'transparent',
      border: escalated ? '1px solid var(--high)' : 'none',
      animation: escalated ? 'sentinel-alert-escalate 2s ease-in-out infinite' : 'none',
      transition: 'background 1.5s',
      alignItems: 'flex-start',
    }}>
      <TypeBadge type={alert.alert_type}/>
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Top row: priority badge + type label + timestamp */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 3, flexWrap: 'wrap' }}>
          <span style={{
            fontSize: 9, fontWeight: 800, color: prio.color,
            background: prio.bg, borderRadius: 3,
            padding: '1px 5px', letterSpacing: .5,
          }}>
            {prio.label}
          </span>
          <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text)' }}>
            {TYPE_LABEL[alert.alert_type] || (alert.alert_type || '').replace(/_/g, ' ')}
          </span>
          {alert._count > 1 && <span style={{ fontSize: 9, fontWeight: 800, color: '#fff', background: 'var(--text2)', borderRadius: 8, padding: '1px 5px' }}>×{alert._count}</span>}
          <span style={{ fontSize: 10, color: 'var(--text2)', marginLeft: 'auto', flexShrink: 0 }}>
            {ts}
          </span>
        </div>

        {alert.details?.plate_text && <div style={{ display: 'inline-block', marginTop: 4, background: '#f5e642', color: '#000', fontFamily: 'monospace', fontWeight: 900, fontSize: 13, letterSpacing: 2, padding: '2px 10px', borderRadius: 4, border: '2px solid #222' }}>{alert.details.plate_text}</div>}
        {alert.details?.global_track_id && <button onClick={() => onOpenSearch?.({ tab: 'track', query: alert.details.global_track_id })} style={{ display: 'block', fontSize: 10, color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', padding: 0, marginTop: 3, textDecoration: 'underline' }}>View journey →</button>}

        {/* Subtitle */}
        <div style={{ fontSize: 11, color: 'var(--text2)', marginBottom: 2, wordBreak: 'break-word' }}>
          {subtitle}
        </div>

        {/* Confidence bar */}
        {alert.confidence > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 3 }}>
            <div style={{ flex: 1, height: 2, background: 'var(--border)', borderRadius: 1 }}>
              <div style={{
                width: `${(alert.confidence * 100).toFixed(0)}%`,
                height: '100%', borderRadius: 1, background: prio.color,
                transition: 'width .4s ease',
              }}/>
            </div>
            <span style={{ fontSize: 9, color: 'var(--text2)', minWidth: 28, textAlign: 'right' }}>
              {(alert.confidence * 100).toFixed(0)}%
            </span>
          </div>
        )}
      </div>

      {alert.cam_id && <img src={`/api/cameras/${alert.cam_id}/snapshot?t=${encodeURIComponent(alert.id || alert.alert_id || '')}`} alt="Alert camera snapshot" style={{ width: 100, height: 56, objectFit: 'cover', borderRadius: 4, flexShrink: 0, border: '1px solid var(--border)' }} onError={event => { event.currentTarget.style.display = 'none' }} />}

      {/* Ack button */}
      {!alert.acknowledged && (
        <button
          onClick={() => onAck(alert.id || alert.alert_id)}
          style={{
            fontSize: 9, padding: '3px 7px', borderRadius: 4, flexShrink: 0,
            border: '1px solid var(--border)', background: 'transparent',
            color: 'var(--text2)', cursor: 'pointer', letterSpacing: .3,
            transition: 'border .15s, color .15s',
          }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.color = 'var(--accent)' }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)';  e.currentTarget.style.color = 'var(--text2)' }}
        >
          ACK
        </button>
      )}
    </div>
  )
}

// ─── Main AlertPanel ──────────────────────────────────────────────────────────
export default function AlertPanel({ alerts, onAck, counts, collapsed = false, onToggle, onOpenSearch }) {
  const [filter, setFilter] = useState('ALL')
  const filters = ['ALL', 'HIGH', 'MEDIUM', 'LOW']

  const grouped = (alerts || []).reduce((acc, alert) => {
    const key = `${alert.alert_type || ''}|${alert.cam_id || ''}|${alert.details?.plate_text || alert.details?.watchlist_name || ''}`
    if (!acc[key]) acc[key] = { ...alert, _count: 1 }
    else acc[key]._count += 1
    return acc
  }, {})
  const visible = Object.values(grouped)
    .sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))
    .filter(a => filter === 'ALL' || a.priority === filter)

  const unacked = (alerts || []).filter(a => !a.acknowledged).length

  if (collapsed) {
    return (
      <div style={{ height: '100%', background: 'var(--surface)', borderLeft: '1px solid var(--border)', display: 'flex', alignItems: 'center', flexDirection: 'column', paddingTop: 10 }}>
        <button onClick={onToggle} title="Expand alerts" aria-label="Expand alerts" style={{ width: 28, height: 28, border: '1px solid var(--border)', borderRadius: 5, background: 'var(--surface2)', color: 'var(--text)', cursor: 'pointer', display: 'grid', placeItems: 'center' }}><BellIcon/></button>
        {unacked > 0 && <span title={`${unacked} unacknowledged alerts`} style={{ marginTop: 8, minWidth: 20, textAlign: 'center', borderRadius: 10, background: 'var(--high)', color: '#fff', fontSize: 10, fontWeight: 700, padding: '3px 2px' }}>{unacked}</span>}
      </div>
    )
  }

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', height: '100%',
      background: 'var(--surface)', borderLeft: '1px solid var(--border)',
    }}>
      <style>{'@keyframes sentinel-alert-escalate{0%,100%{border-color:var(--high)}50%{border-color:transparent}}'}</style>
      {/* Header */}
      <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <span style={{ fontWeight: 700, fontSize: 13, letterSpacing: .3 }}>
            Alerts
          </span>
          <button onClick={onToggle} title="Collapse alerts" aria-label="Collapse alerts" style={{ marginLeft: 'auto', marginRight: 7, width: 26, height: 24, border: '1px solid var(--border)', borderRadius: 4, background: 'transparent', color: 'var(--text2)', cursor: 'pointer', display: 'grid', placeItems: 'center' }}><BellIcon muted/></button>
          {unacked > 0 && (
            <span style={{
              fontSize: 10, fontWeight: 700, color: 'var(--high)',
              background: 'rgba(248,81,73,.1)', borderRadius: 4, padding: '1px 6px',
            }}>
              {unacked} pending
            </span>
          )}
        </div>

        {/* Summary counters */}
        {counts && (
          <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
            {[
              ['H', counts.high,   PRIO.HIGH.color,   PRIO.HIGH.bg  ],
              ['M', counts.medium, PRIO.MEDIUM.color, PRIO.MEDIUM.bg],
              ['L', counts.low,    PRIO.LOW.color,    PRIO.LOW.bg   ],
            ].map(([l, v, c, bg]) => (
              <div key={l} style={{
                flex: 1, background: bg, borderRadius: 5, padding: '5px 4px', textAlign: 'center',
              }}>
                <div style={{ fontSize: 15, fontWeight: 800, color: c, lineHeight: 1 }}>{v || 0}</div>
                <div style={{ fontSize: 9, color: 'var(--text2)', marginTop: 2, letterSpacing: .3 }}>{l}</div>
              </div>
            ))}
            <div style={{
              flex: 1.5, background: 'var(--surface2)', borderRadius: 5,
              padding: '5px 4px', textAlign: 'center', border: '1px solid var(--border)',
            }}>
              <div style={{ fontSize: 15, fontWeight: 800, color: 'var(--text)', lineHeight: 1 }}>
                {counts.last_hour || 0}
              </div>
              <div style={{ fontSize: 9, color: 'var(--text2)', marginTop: 2, letterSpacing: .3 }}>
                /hr
              </div>
            </div>
          </div>
        )}

        {/* Filter tabs */}
        <div style={{ display: 'flex', gap: 3, background: 'var(--surface2)', borderRadius: 6, padding: 2 }}>
          {filters.map(f => (
            <button key={f} onClick={() => setFilter(f)} style={{
              flex: 1, padding: '4px 0', border: 'none', borderRadius: 4, fontSize: 10,
              background: filter === f ? 'var(--surface)' : 'transparent',
              color: filter === f ? 'var(--text)' : 'var(--text2)',
              cursor: 'pointer', fontWeight: filter === f ? 700 : 400,
              boxShadow: filter === f ? '0 1px 3px rgba(0,0,0,.3)' : 'none',
              transition: 'all .15s', letterSpacing: .3,
            }}>
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* Alert list */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {visible.length === 0 ? (
          <div style={{ padding: 32, textAlign: 'center', color: 'var(--text2)', fontSize: 12 }}>
            {filter === 'ALL' ? 'No alerts yet' : `No ${filter} alerts`}
          </div>
        ) : (
          visible.map((a, i) => (
            <AlertRow key={a.alert_id || a.id || i} alert={a} onAck={onAck} onOpenSearch={onOpenSearch}/>
          ))
        )}
      </div>
    </div>
  )
}
