import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'

const PRIO = {
  HIGH: { color: 'var(--high)', bg: 'rgba(248,81,73,.10)', label: 'HIGH' },
  MEDIUM: { color: 'var(--medium)', bg: 'rgba(210,153,34,.10)', label: 'MED' },
  LOW: { color: 'var(--low)', bg: 'rgba(63,185,80,.10)', label: 'LOW' },
}
const TYPE_LABEL = { watchlist_match: 'Watchlist Match', cross_camera_sighting: 'Cross-Camera', anomaly_running_crowd: 'Running / Crowd', anomaly_crowd_formation: 'Crowd Detected', anomaly_abandoned_object: 'Abandoned Object', test_plate_detected: 'Test Plate Detected' }
const STATUS_LABEL = { NEW: 'New', ACKNOWLEDGED: 'Acknowledged', INVESTIGATING: 'Investigating', RESOLVED: 'Resolved', CLOSED: 'Closed' }
const NEXT_ACTIONS = { NEW: ['ACKNOWLEDGED'], ACKNOWLEDGED: ['INVESTIGATING', 'RESOLVED'], INVESTIGATING: ['RESOLVED'], RESOLVED: ['CLOSED'], CLOSED: [] }
const BellIcon = ({ muted = false }) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 0-3.46 0"/>{muted && <path d="m4 4 16 16"/>}</svg>
const StatusDot = ({ status }) => <span style={{ width: 7, height: 7, borderRadius: '50%', background: status === 'NEW' ? 'var(--high)' : status === 'ACKNOWLEDGED' ? 'var(--accent)' : status === 'INVESTIGATING' ? 'var(--medium)' : 'var(--text2)', flexShrink: 0 }} aria-hidden="true"/>

function AlertRow({ alert, onTransition, onOpenSearch }) {
  const prio = PRIO[alert.priority] || PRIO.MEDIUM
  const status = String(alert.status || (alert.acknowledged ? 'ACKNOWLEDGED' : 'NEW')).toUpperCase()
  const raw = alert.event_timestamp || alert.timestamp || alert.created_at || alert.event_at
  const date = typeof raw === 'number' || !Number.isNaN(Number(raw)) ? new Date(Number(raw) * 1000) : new Date(raw)
  const ts = Number.isNaN(date.getTime()) ? '—' : date.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
  const ageMs = Date.now() - date.getTime()
  const escalated = status === 'NEW' && Number.isFinite(ageMs) && ageMs > 5 * 60 * 1000
  const subtitle = alert.details?.watchlist_name || alert.details?.message || alert.details?.anomaly_type?.replace(/_/g, ' ') || alert.details?.description || (alert.cam_name ? `Camera ${alert.cam_name}` : (alert.cam_id ? `Camera ${alert.cam_id.slice(0, 8)}` : alert.camera_label || '—'))
  return <div style={{ display: 'flex', gap: 8, padding: '8px 12px', borderBottom: '1px solid var(--border)', background: alert._new ? 'rgba(88,166,255,.04)' : 'transparent', border: escalated ? '1px solid var(--high)' : undefined, alignItems: 'flex-start' }}>
    <StatusDot status={status}/>
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 3, flexWrap: 'wrap' }}><span style={{ fontSize: 9, fontWeight: 800, color: prio.color, background: prio.bg, borderRadius: 3, padding: '1px 5px' }}>{prio.label}</span><span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text)' }}>{TYPE_LABEL[alert.alert_type] || (alert.alert_type || '').replace(/_/g, ' ')}</span><span style={{ fontSize: 9, color: 'var(--text2)', border: '1px solid var(--border)', borderRadius: 3, padding: '1px 4px' }}>{STATUS_LABEL[status] || status}</span><span style={{ fontSize: 10, color: 'var(--text2)', marginLeft: 'auto' }}>{ts}</span></div>
      {alert.details?.plate_text && <div style={{ display: 'inline-block', marginTop: 4, background: '#f5e642', color: '#000', fontFamily: 'monospace', fontWeight: 900, fontSize: 13, letterSpacing: 2, padding: '2px 10px', borderRadius: 4, border: '2px solid #222' }}>{alert.details.plate_text}</div>}
      {alert.details?.global_track_id && <button onClick={() => onOpenSearch?.({ tab: 'track', query: alert.details.global_track_id })} style={{ display: 'block', fontSize: 10, color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', padding: 0, marginTop: 3, textDecoration: 'underline' }}>View journey</button>}
      <div style={{ fontSize: 11, color: 'var(--text2)', marginTop: 3, marginBottom: 3, wordBreak: 'break-word' }}>{subtitle}</div>
      {alert.confidence > 0 && <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 3 }}><div style={{ flex: 1, height: 2, background: 'var(--border)', borderRadius: 1 }}><div style={{ width: `${Math.min(100, Number(alert.confidence) * 100).toFixed(0)}%`, height: '100%', borderRadius: 1, background: prio.color }}/></div><span style={{ fontSize: 9, color: 'var(--text2)' }}>{(Number(alert.confidence) * 100).toFixed(0)}%</span></div>}
      <div style={{ display: 'flex', gap: 4, marginTop: 6, flexWrap: 'wrap' }}>{NEXT_ACTIONS[status].map(target => <button key={target} onClick={() => onTransition(alert, target)} title={STATUS_LABEL[target]} aria-label={`${STATUS_LABEL[target]} alert`} style={{ fontSize: 9, padding: '3px 7px', borderRadius: 4, border: '1px solid var(--border)', background: target === 'ACKNOWLEDGED' ? 'var(--surface2)' : 'transparent', color: 'var(--text)', cursor: 'pointer' }}>{target === 'ACKNOWLEDGED' ? 'ACK' : target === 'INVESTIGATING' ? 'Investigate' : target === 'RESOLVED' ? 'Resolve' : 'Close'}</button>)}</div>
    </div>
    {alert.cam_id && <img src={`/api/cameras/${alert.cam_id}/snapshot?t=${encodeURIComponent(alert.id || alert.alert_id || '')}`} alt="Alert evidence snapshot" style={{ width: 100, height: 56, objectFit: 'cover', borderRadius: 4, flexShrink: 0, border: '1px solid var(--border)' }} onError={event => { event.currentTarget.style.display = 'none' }}/>} 
  </div>
}

export default function AlertPanel({ alerts, onAck, counts, collapsed = false, onToggle, onOpenSearch, isTest = false, testSessionId = null }) {
  const [filter, setFilter] = useState('ALL')
  const [localStatus, setLocalStatus] = useState({})
  const [busy, setBusy] = useState({})
  const filters = ['ALL', 'HIGH', 'MEDIUM', 'LOW']
  const inferredTest = isTest || Boolean(testSessionId) || (alerts || []).some(alert => Boolean(alert.session_id))
  const inferredSessionId = testSessionId || (alerts || []).find(alert => alert.session_id)?.session_id || null
  useEffect(() => { setLocalStatus(previous => { const next = { ...previous }; (alerts || []).forEach(a => { const id = a.id || a.alert_id; if (id) next[id] = a.status || (a.acknowledged ? 'ACKNOWLEDGED' : 'NEW') }); return next }) }, [alerts])
  const grouped = useMemo(() => (alerts || []).reduce((acc, alert) => { const key = `${alert.alert_type || ''}|${alert.cam_id || alert.camera_label || ''}|${alert.details?.plate_text || alert.details?.watchlist_name || ''}`; if (!acc[key]) acc[key] = { ...alert, _count: 1 }; else acc[key]._count += 1; return acc }, {}), [alerts])
  const visible = Object.values(grouped).map(alert => ({ ...alert, status: localStatus[alert.id || alert.alert_id] || alert.status || (alert.acknowledged ? 'ACKNOWLEDGED' : 'NEW') })).sort((a, b) => new Date(b.created_at || b.event_at || 0) - new Date(a.created_at || a.event_at || 0)).filter(a => filter === 'ALL' || a.priority === filter)
  const unacked = (alerts || []).filter(a => (localStatus[a.id || a.alert_id] || a.status || (a.acknowledged ? 'ACKNOWLEDGED' : 'NEW')) === 'NEW').length
  const transition = async (alert, target) => { const id = alert.id || alert.alert_id; if (!id || busy[id]) return; const sessionId = alert.session_id || inferredSessionId; if (inferredTest && !sessionId) return; setBusy(v => ({ ...v, [id]: true })); try { const result = inferredTest ? await api.transitionTestAlert(sessionId, id, target) : await api.transitionAlert(id, target); setLocalStatus(v => ({ ...v, [id]: result.status || target })); if (target === 'ACKNOWLEDGED') onAck?.(id) } catch (error) { console.warn('alert transition failed:', error) } finally { setBusy(v => ({ ...v, [id]: false })) } }

  if (collapsed) return <div style={{ height: '100%', background: 'var(--surface)', borderLeft: '1px solid var(--border)', display: 'flex', alignItems: 'center', flexDirection: 'column', paddingTop: 10 }}><button onClick={onToggle} title="Expand alerts" aria-label="Expand alerts" style={{ width: 28, height: 28, border: '1px solid var(--border)', borderRadius: 5, background: 'var(--surface2)', color: 'var(--text)', cursor: 'pointer', display: 'grid', placeItems: 'center' }}><BellIcon/></button>{unacked > 0 && <span title={`${unacked} unacknowledged alerts`} style={{ marginTop: 8, minWidth: 20, textAlign: 'center', borderRadius: 10, background: 'var(--high)', color: '#fff', fontSize: 10, fontWeight: 700, padding: '3px 2px' }}>{unacked}</span>}</div>
  return <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--surface)', borderLeft: '1px solid var(--border)' }}>
    <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}><div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}><span style={{ fontWeight: 700, fontSize: 13 }}>Alerts</span><button onClick={onToggle} title="Collapse alerts" aria-label="Collapse alerts" style={{ marginLeft: 'auto', marginRight: 7, width: 26, height: 24, border: '1px solid var(--border)', borderRadius: 4, background: 'transparent', color: 'var(--text2)', cursor: 'pointer', display: 'grid', placeItems: 'center' }}><BellIcon muted/></button>{unacked > 0 && <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--high)', background: 'rgba(248,81,73,.1)', borderRadius: 4, padding: '1px 6px' }}>{unacked} pending</span>}</div>
      {counts && <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>{[['H', counts.high, PRIO.HIGH], ['M', counts.medium, PRIO.MEDIUM], ['L', counts.low, PRIO.LOW]].map(([l, v, p]) => <div key={l} style={{ flex: 1, background: p.bg, borderRadius: 5, padding: '5px 4px', textAlign: 'center' }}><div style={{ fontSize: 15, fontWeight: 800, color: p.color }}>{v || 0}</div><div style={{ fontSize: 9, color: 'var(--text2)', marginTop: 2 }}>{l}</div></div>)}</div>}
      <div style={{ display: 'flex', gap: 3, background: 'var(--surface2)', borderRadius: 6, padding: 2 }}>{filters.map(f => <button key={f} onClick={() => setFilter(f)} style={{ flex: 1, padding: '4px 0', border: 'none', borderRadius: 4, fontSize: 10, background: filter === f ? 'var(--surface)' : 'transparent', color: filter === f ? 'var(--text)' : 'var(--text2)', cursor: 'pointer', fontWeight: filter === f ? 700 : 400 }}>{f}</button>)}</div>
    </div>
    <div style={{ flex: 1, overflowY: 'auto' }}>{visible.length === 0 ? <div style={{ padding: 32, textAlign: 'center', color: 'var(--text2)', fontSize: 12 }}>No alerts</div> : visible.map((a, i) => <AlertRow key={a.alert_id || a.id || i} alert={a} onTransition={transition} onOpenSearch={onOpenSearch}/>)}</div>
  </div>
}
