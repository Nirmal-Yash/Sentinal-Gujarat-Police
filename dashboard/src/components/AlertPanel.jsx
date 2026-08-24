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
function AlertRow({ alert, onAck }) {
  const prio = PRIO[alert.priority] || PRIO.MEDIUM
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
          <span style={{ fontSize: 10, color: 'var(--text2)', marginLeft: 'auto', flexShrink: 0 }}>
            {ts}
          </span>
        </div>

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

      {/* Ack button */}
      {!alert.acknowledged && (
        <button
          onClick={() => onAck(alert.alert_id || alert.id)}
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
export default function AlertPanel({ alerts, onAck, counts }) {
  const [filter, setFilter] = useState('ALL')
  const filters = ['ALL', 'HIGH', 'MEDIUM', 'LOW']

  const visible = filter === 'ALL' ? alerts
    : alerts.filter(a => a.priority === filter)

  const unacked = (alerts || []).filter(a => !a.acknowledged).length

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', height: '100%',
      background: 'var(--surface)', borderLeft: '1px solid var(--border)',
    }}>
      {/* Header */}
      <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <span style={{ fontWeight: 700, fontSize: 13, letterSpacing: .3 }}>
            Alerts
          </span>
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
            <AlertRow key={a.alert_id || a.id || i} alert={a} onAck={onAck}/>
          ))
        )}
      </div>
    </div>
  )
}
