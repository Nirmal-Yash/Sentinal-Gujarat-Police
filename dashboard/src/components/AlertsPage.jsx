import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'

const STATUS_CONFIG = {
  NEW: { label: 'New', tone: '#ef4444', bg: 'rgba(239,68,68,.12)', border: 'rgba(239,68,68,.35)' },
  ACKNOWLEDGED: { label: 'Acknowledged', tone: '#f59e0b', bg: 'rgba(245,158,11,.12)', border: 'rgba(245,158,11,.35)' },
  INVESTIGATING: { label: 'Investigating', tone: '#60a5fa', bg: 'rgba(96,165,250,.12)', border: 'rgba(96,165,250,.35)' },
  RESOLVED: { label: 'Resolved', tone: '#22c55e', bg: 'rgba(34,197,94,.12)', border: 'rgba(34,197,94,.35)' },
  CLOSED: { label: 'Closed', tone: '#a1a1aa', bg: 'rgba(161,161,170,.10)', border: 'rgba(161,161,170,.25)' },
}

const TYPE_CONFIG = {
  WATCHLIST_HIT: { label: 'Watchlist Hit', icon: '⚠', tone: '#ef4444' },
  PLATE_SIGHTING: { label: 'Plate Sighting', icon: '▣', tone: '#fb923c' },
  CROWD_ANOMALY: { label: 'Crowd Anomaly', icon: '◉', tone: '#c084fc' },
  RUNNING_CROWD: { label: 'Running Crowd', icon: '!', tone: '#ef4444' },
  ANOMALY_CROWD_FORMATION: { label: 'Crowd Formation', icon: '◉', tone: '#c084fc' },
  ANOMALY_RUNNING_CROWD: { label: 'Running Crowd', icon: '!', tone: '#ef4444' },
  ANOMALY_ABANDONED_OBJECT: { label: 'Abandoned Object', icon: '◈', tone: '#f59e0b' },
}

const SEVERITY_CONFIG = {
  critical: { label: 'Critical', tone: '#ef4444', border: '#ef4444' },
  high: { label: 'High', tone: '#f97316', border: '#f97316' },
  medium: { label: 'Medium', tone: '#f59e0b', border: '#f59e0b' },
  low: { label: 'Low', tone: '#a1a1aa', border: '#52525b' },
}

const STATUS_OPTIONS = ['ALL', 'NEW', 'ACKNOWLEDGED', 'INVESTIGATING', 'RESOLVED', 'CLOSED']
const PRIORITY_OPTIONS = ['ALL', 'HIGH', 'MEDIUM', 'LOW']

function alertType(alert) {
  return String(alert?.anomaly_type || alert?.alert_type || 'SYSTEM').toUpperCase()
}

function severityFor(alert) {
  const priority = String(alert?.priority || '').toUpperCase()
  const score = Number(alert?.score ?? alert?.confidence ?? 0)
  if (priority === 'CRITICAL' || alertType(alert).includes('RUNNING') || score > 0.9) return 'critical'
  if (priority === 'HIGH' || score > 0.75) return 'high'
  if (priority === 'MEDIUM' || score > 0.5) return 'medium'
  return 'low'
}

function formatTime(value) {
  if (!value) return '—'
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('en-IN', { hour12: false })
}

function formatRelative(value) {
  if (!value) return '—'
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value)
  const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000))
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

function Badge({ label, tone, bg, border }) {
  return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, minHeight: 22, padding: '0 8px', borderRadius: 999, background: bg || `${tone}18`, border: `1px solid ${border || `${tone}40`}`, color: tone, fontSize: 9, fontWeight: 850, letterSpacing: '.2px', whiteSpace: 'nowrap' }}><span style={{ width: 5, height: 5, borderRadius: '50%', background: tone }} />{label}</span>
}

function TypeBadge({ alert }) {
  const cfg = TYPE_CONFIG[alertType(alert)] || { label: alertType(alert).replace(/_/g, ' '), icon: '•', tone: '#a1a1aa' }
  return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, minHeight: 22, padding: '0 8px', borderRadius: 7, background: `${cfg.tone}12`, border: `1px solid ${cfg.tone}30`, color: cfg.tone, fontSize: 9, fontWeight: 850, whiteSpace: 'nowrap' }}><span>{cfg.icon}</span>{cfg.label}</span>
}

function ActionButton({ label, disabled, tone = 'var(--accent)', onClick }) {
  return <button type="button" onClick={onClick} disabled={disabled} style={{ border: `1px solid ${tone}55`, background: `${tone}14`, color: tone, borderRadius: 7, minHeight: 30, padding: '0 10px', fontSize: 9, fontWeight: 850, cursor: disabled ? 'default' : 'pointer', opacity: disabled ? .6 : 1 }}>{disabled ? `${label}…` : label}</button>
}

function AlertEvidence({ alert }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let active = true
    const load = async () => {
      if (!alert?.id && !alert?.alert_id) return
      setLoading(true)
      setFailed(false)
      try {
        const result = await api.listEvidence({ alert_id: alert.id || alert.alert_id, limit: 10 })
        if (active) setItems(Array.isArray(result) ? result : [])
      } catch {
        if (active) setFailed(true)
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    return () => { active = false }
  }, [alert?.id, alert?.alert_id])

  const fallbackKey = alert?.details?.evidence_storage_key
  if (loading) return <div style={evidenceBox}>Loading evidence…</div>
  if (items.length === 0 && !fallbackKey) return null
  if (failed && !fallbackKey) return <div style={evidenceBox}>Evidence metadata unavailable.</div>

  const fallbackId = alert?.details?.evidence_id
  return <div style={{ marginTop: 14 }}>
    <div style={{ fontSize: 9, fontWeight: 850, letterSpacing: '.5px', color: 'var(--text2)', textTransform: 'uppercase', marginBottom: 8 }}>Evidence</div>
    <div style={{ display: 'grid', gap: 9 }}>
      {items.map(item => <EvidenceItem key={item.id} item={item} />)}
      {!items.length && fallbackId && <img src={`/api/evidence/${fallbackId}/content`} alt="Alert evidence" style={evidenceImage} />}
    </div>
  </div>
}

function EvidenceItem({ item }) {
  const [failed, setFailed] = useState(false)
  if (failed) return <div style={evidenceBox}>Evidence content unavailable.</div>
  return <div style={{ background: '#050505', border: '1px solid var(--border)', borderRadius: 9, overflow: 'hidden' }}>
    <img src={`/api/evidence/${item.id}/content`} alt="Alert evidence" style={evidenceImage} onError={() => setFailed(true)} />
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, padding: '7px 9px', fontSize: 8, color: 'var(--text2)' }}>
      <span>{item.captured_at ? formatTime(item.captured_at) : item.media_type || 'Evidence'}</span>
      {item.sha256 && <span title={item.sha256} style={{ fontFamily: 'monospace' }}>SHA256 {item.sha256.slice(0, 16)}…</span>}
    </div>
  </div>
}

const evidenceImage = { display: 'block', width: '100%', maxHeight: 300, objectFit: 'contain', background: '#000' }
const evidenceBox = { padding: 12, borderRadius: 8, border: '1px solid var(--border)', background: 'var(--surface2)', color: 'var(--text2)', fontSize: 9 }

export default function AlertsPage({ initialAlerts = [], onTransition, onOpenInvestigation }) {
  const [alerts, setAlerts] = useState(initialAlerts || [])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState(null)
  const [actionPending, setActionPending] = useState(null)
  const [error, setError] = useState('')
  const [filters, setFilters] = useState({ priority: 'ALL', status: 'ALL', camera: '', plate: '', from: '', to: '' })
  const [datePreset, setDatePreset] = useState('ALL TIME')
  const requestSeq = useRef(0)

  const load = useCallback(async () => {
    const requestId = ++requestSeq.current
    setLoading(true)
    setError('')
    const query = {
      limit: 300,
      ...(filters.priority !== 'ALL' ? { priority: filters.priority } : {}),
      ...(filters.status !== 'ALL' ? { status: filters.status } : {}),
      ...(filters.camera ? { camera_id: filters.camera } : {}),
      ...(filters.plate ? { plate: filters.plate } : {}),
      ...(filters.from ? { from: filters.from } : {}),
      ...(filters.to ? { to: filters.to } : {}),
    }
    try {
      const result = await api.getAlerts(query)
      if (requestId === requestSeq.current) setAlerts(Array.isArray(result) ? result : [])
    } catch (err) {
      if (requestId === requestSeq.current) setError(err?.message || 'Failed to load alerts')
    } finally {
      if (requestId === requestSeq.current) setLoading(false)
    }
  }, [filters])

  useEffect(() => { setAlerts(initialAlerts || []) }, [initialAlerts])
  useEffect(() => { load() }, [filters.priority, filters.status, filters.camera, filters.plate, filters.from, filters.to])
  useEffect(() => {
    const timer = setInterval(load, 30000)
    return () => clearInterval(timer)
  }, [load])

  const visible = useMemo(() => (alerts || []).filter(a => {
    const text = `${a.details?.plate_text || ''} ${a.cam_name || a.camera_label || ''} ${a.alert_type || ''}`.toLowerCase()
    if (filters.camera && !text.includes(filters.camera.toLowerCase())) return false
    if (filters.plate && !String(a.details?.plate_text || '').toLowerCase().includes(filters.plate.toLowerCase())) return false
    return true
  }), [alerts, filters.camera, filters.plate])

  const unacknowledged = visible.filter(a => !a.acknowledged && String(a.status || 'NEW') === 'NEW').length
  const critical = visible.filter(a => severityFor(a) === 'critical').length
  const high = visible.filter(a => severityFor(a) === 'high').length

  const setPreset = preset => {
    const today = new Date()
    const start = new Date(today)
    if (preset === 'LAST HOUR') start.setHours(today.getHours() - 1)
    if (preset === 'LAST 24H') start.setDate(today.getDate() - 1)
    if (preset === 'LAST 7D') start.setDate(today.getDate() - 7)
    if (preset === 'LAST 30D') start.setDate(today.getDate() - 30)
    if (preset === 'ALL TIME') {
      setFilters(f => ({ ...f, from: '', to: '' }))
    } else {
      const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
      setFilters(f => ({ ...f, from: iso(start), to: iso(today) }))
    }
    setDatePreset(preset)
  }

  const transition = async (alert, target) => {
    const id = alert.id || alert.alert_id
    if (!id) return
    setActionPending(`${id}:${target}`)
    setError('')
    try {
      await onTransition?.(alert, target)
      setAlerts(v => v.map(x => (x.id || x.alert_id) === id ? { ...x, status: target, acknowledged: target !== 'NEW' } : x))
      setSelected(v => v && (v.id || v.alert_id) === id ? { ...v, status: target, acknowledged: target !== 'NEW' } : v)
    } catch (err) {
      setError(err?.message || `Unable to ${target.toLowerCase()} alert`)
    } finally {
      setActionPending(null)
    }
  }

  return <div className="sentinel-alerts-page" style={{ height: '100%', width: '100%', flex: '1 1 auto', minWidth: 0, background: 'var(--bg)', color: 'var(--text)', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
    <header style={{ padding: '15px 18px 12px', borderBottom: '1px solid var(--border)', background: 'var(--surface)', flex: '0 0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14, flexWrap: 'wrap' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}><h1 style={{ margin: 0, fontSize: 20, fontWeight: 850 }}>Alerts</h1><span style={{ fontSize: 9, color: 'var(--text2)', padding: '3px 7px', borderRadius: 999, background: 'var(--surface2)', border: '1px solid var(--border)' }}>{visible.length} visible</span></div>
          <div style={{ marginTop: 4, fontSize: 10, color: 'var(--text2)' }}>Operator queue · evidence · lifecycle</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {critical > 0 && <Badge label={`${critical} Critical`} tone="#ef4444" />}
          {high > 0 && <Badge label={`${high} High`} tone="#f97316" />}
          {unacknowledged > 0 && <Badge label={`${unacknowledged} New`} tone="#f59e0b" />}
          <button type="button" onClick={load} disabled={loading} style={{ padding: '8px 12px', border: 0, borderRadius: 7, background: 'var(--accent)', color: '#111', fontSize: 10, fontWeight: 850, cursor: loading ? 'default' : 'pointer', opacity: loading ? .65 : 1 }}>{loading ? 'Refreshing…' : 'Refresh'}</button>
        </div>
      </div>

      <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: 'repeat(6,minmax(0,1fr))', gap: 7 }}>
        <select value={filters.priority} onChange={e => setFilters(f => ({ ...f, priority: e.target.value }))} style={fieldStyle}>{PRIORITY_OPTIONS.map(v => <option key={v}>{v}</option>)}</select>
        <select value={filters.status} onChange={e => setFilters(f => ({ ...f, status: e.target.value }))} style={fieldStyle}>{STATUS_OPTIONS.map(v => <option key={v}>{v}</option>)}</select>
        <input value={filters.camera} onChange={e => setFilters(f => ({ ...f, camera: e.target.value }))} placeholder="Camera / ID" style={fieldStyle} />
        <input value={filters.plate} onChange={e => setFilters(f => ({ ...f, plate: e.target.value }))} placeholder="Plate" style={fieldStyle} />
        <div style={{ display: 'flex', gap: 5, minWidth: 0 }}>
          <select value={datePreset} onChange={e => setPreset(e.target.value)} style={{ ...fieldStyle, flex: 1 }}><option>ALL TIME</option><option>LAST HOUR</option><option>LAST 24H</option><option>LAST 7D</option><option>LAST 30D</option></select>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 5, minWidth: 0 }}><input type="date" aria-label="From date" value={filters.from} onChange={e => { setDatePreset('CUSTOM'); setFilters(f => ({ ...f, from: e.target.value })) }} style={fieldStyle} /><input type="date" aria-label="To date" value={filters.to} onChange={e => { setDatePreset('CUSTOM'); setFilters(f => ({ ...f, to: e.target.value })) }} style={fieldStyle} /></div>
      </div>
      {error && <div style={{ marginTop: 9, padding: '7px 9px', borderRadius: 7, border: '1px solid rgba(239,68,68,.28)', background: 'rgba(239,68,68,.08)', color: '#fca5a5', fontSize: 9 }}>{error}</div>}
    </header>

    <main style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: 12 }}>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 11, overflow: 'hidden', minHeight: '100%' }}>
        {visible.length === 0 ? <div style={{ padding: 50, textAlign: 'center', color: 'var(--text2)', fontSize: 11 }}>No alerts match the selected filters.</div> : <div>
          {visible.map((alert, index) => <div key={alert.id || alert.alert_id} className="sentinel-alert-row" style={{ ...rowStyle, animationDelay: `${Math.min(index, 12) * 18}ms`, borderLeft: `3px solid ${SEVERITY_CONFIG[severityFor(alert)].border}` }}>
            <button type="button" onClick={() => setSelected(alert)} style={{ ...rowButton, textAlign: 'left' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, minWidth: 0, flexWrap: 'wrap' }}><TypeBadge alert={alert}/><Badge label={STATUS_CONFIG[String(alert.status || 'NEW').toUpperCase()]?.label || String(alert.status || 'NEW')} {...STATUS_CONFIG[String(alert.status || 'NEW').toUpperCase()] || STATUS_CONFIG.NEW} /></div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0, marginTop: 7 }}><strong style={{ fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{alert.details?.plate_text || alert.details?.watchlist_name || alert.details?.message || 'System event'}</strong><span style={{ fontSize: 9, color: 'var(--text2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{alert.cam_name || alert.camera_label || alert.cam_id || 'Unknown camera'}</span></div>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, marginTop: 5 }}><span style={{ fontSize: 8, color: 'var(--text2)' }}>{formatRelative(alert.created_at || alert.event_at)}</span><span style={{ fontSize: 8, color: SEVERITY_CONFIG[severityFor(alert)].tone, fontWeight: 850 }}>{SEVERITY_CONFIG[severityFor(alert)].label}</span></div>
            </button>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, paddingRight: 9 }}>
              {String(alert.status || 'NEW') === 'NEW' && <ActionButton label="Acknowledge" tone="#f59e0b" disabled={actionPending === `${alert.id || alert.alert_id}:ACKNOWLEDGED`} onClick={() => transition(alert, 'ACKNOWLEDGED')} />}
              {String(alert.status || '') === 'ACKNOWLEDGED' && <ActionButton label="Investigate" tone="#60a5fa" disabled={actionPending === `${alert.id || alert.alert_id}:INVESTIGATING`} onClick={() => transition(alert, 'INVESTIGATING')} />}
              {String(alert.status || '') === 'INVESTIGATING' && <ActionButton label="Resolve" tone="#22c55e" disabled={actionPending === `${alert.id || alert.alert_id}:RESOLVED`} onClick={() => transition(alert, 'RESOLVED')} />}
              {String(alert.status || '') === 'RESOLVED' && <ActionButton label="Close" tone="#a1a1aa" disabled={actionPending === `${alert.id || alert.alert_id}:CLOSED`} onClick={() => transition(alert, 'CLOSED')} />}
            </div>
          </div>)}
        </div>}
      </div>
    </main>

    {selected && <div style={drawerOverlay} onClick={e => e.target === e.currentTarget && setSelected(null)}>
      <aside style={drawer} role="dialog" aria-modal="true" aria-label="Alert details">
        <header style={drawerHeader}><div style={{ minWidth: 0 }}><div style={{ display: 'flex', gap: 7, flexWrap: 'wrap' }}><TypeBadge alert={selected}/><Badge label={STATUS_CONFIG[String(selected.status || 'NEW').toUpperCase()]?.label || String(selected.status || 'NEW')} {...STATUS_CONFIG[String(selected.status || 'NEW').toUpperCase()] || STATUS_CONFIG.NEW} /><Badge label={SEVERITY_CONFIG[severityFor(selected)].label} tone={SEVERITY_CONFIG[severityFor(selected)].tone} /></div><div style={{ marginTop: 8, fontSize: 14, fontWeight: 850, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{selected.details?.plate_text || selected.details?.watchlist_name || selected.details?.message || 'Alert details'}</div><div style={{ marginTop: 3, fontSize: 9, color: 'var(--text2)' }}>{selected.cam_name || selected.camera_label || selected.cam_id || 'Camera'} · {formatTime(selected.created_at || selected.event_at)}</div></div><button type="button" onClick={() => setSelected(null)} aria-label="Close alert details" style={closeBtn}>×</button></header>
        <div style={{ flex: 1, overflow: 'auto', padding: 15 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,minmax(0,1fr))', gap: 7, marginBottom: 12 }}><Metric label="Priority" value={selected.priority || 'MEDIUM'} /><Metric label="Confidence" value={selected.confidence != null ? `${(Number(selected.confidence) * 100).toFixed(0)}%` : '—'} /><Metric label="Camera" value={selected.cam_name || selected.camera_label || selected.cam_id || '—'} /><Metric label="Time" value={formatTime(selected.created_at || selected.event_at)} /></div>
          {selected.details?.plate_text && <div style={{ fontFamily: 'monospace', fontSize: 19, fontWeight: 900, letterSpacing: 2, padding: '10px 13px', borderRadius: 8, background: '#f5f5f5', color: '#111', display: 'inline-block', marginBottom: 12 }}>{selected.details.plate_text}</div>}
          <AlertEvidence alert={selected}/>
          <section style={{ marginTop: 15 }}><div style={sectionTitle}>Event details</div><pre style={detailsPre}>{JSON.stringify(selected.details || {}, null, 2)}</pre></section>
          <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', marginTop: 14 }}>
            {String(selected.status || 'NEW') === 'NEW' && <ActionButton label="Acknowledge" tone="#f59e0b" disabled={Boolean(actionPending)} onClick={() => transition(selected, 'ACKNOWLEDGED')} />}
            {String(selected.status || '') === 'ACKNOWLEDGED' && <ActionButton label="Investigate" tone="#60a5fa" disabled={Boolean(actionPending)} onClick={() => transition(selected, 'INVESTIGATING')} />}
            {String(selected.status || '') === 'INVESTIGATING' && <ActionButton label="Resolve" tone="#22c55e" disabled={Boolean(actionPending)} onClick={() => transition(selected, 'RESOLVED')} />}
            {String(selected.status || '') === 'RESOLVED' && <ActionButton label="Close" tone="#a1a1aa" disabled={Boolean(actionPending)} onClick={() => transition(selected, 'CLOSED')} />}
            {selected.details?.plate_text && <ActionButton label="Investigate plate" tone="#60a5fa" onClick={() => onOpenInvestigation?.({ tab: 'plate', query: selected.details.plate_text })} />}
          </div>
        </div>
      </aside>
    </div>}
  </div>
}

function Metric({ label, value }) {
  return <div style={{ padding: 9, borderRadius: 8, background: 'var(--surface2)', border: '1px solid var(--border)' }}><div style={{ fontSize: 8, color: 'var(--muted)', fontWeight: 750 }}>{label}</div><div style={{ fontSize: 10, marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{value}</div></div>
}

const fieldStyle = { width: '100%', boxSizing: 'border-box', padding: '8px 9px', border: '1px solid var(--border)', borderRadius: 7, background: 'var(--surface2)', color: 'var(--text)', fontSize: 10, minWidth: 0 }
const rowStyle = { display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto', gap: 10, alignItems: 'stretch', padding: '10px 0', borderBottom: '1px solid rgba(255,255,255,.07)', animation: 'sentinelAlertIn .18s ease both' }
const rowButton = { width: '100%', minWidth: 0, border: 0, background: 'transparent', color: 'var(--text)', padding: '1px 8px 1px 12px', cursor: 'pointer' }
const drawerOverlay = { position: 'fixed', inset: 0, zIndex: 2000, background: 'rgba(0,0,0,.72)', display: 'flex', justifyContent: 'flex-end' }
const drawer = { width: 'min(700px,94vw)', height: '100%', background: '#050505', borderLeft: '1px solid var(--border)', display: 'flex', flexDirection: 'column', boxShadow: '-20px 0 60px rgba(0,0,0,.55)', animation: 'sentinelDrawerIn .18s ease both' }
const drawerHeader = { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, padding: '15px 17px', borderBottom: '1px solid var(--border)' }
const closeBtn = { width: 32, height: 32, flex: '0 0 auto', border: '1px solid var(--border)', borderRadius: 7, background: 'var(--surface2)', color: 'var(--text)', fontSize: 18, cursor: 'pointer' }
const sectionTitle = { fontSize: 9, fontWeight: 850, letterSpacing: '.5px', color: 'var(--text2)', textTransform: 'uppercase', marginBottom: 7 }
const detailsPre = { whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 9, lineHeight: 1.5, color: 'var(--text2)', background: 'var(--surface2)', border: '1px solid var(--border)', padding: 11, borderRadius: 8, margin: 0 }
