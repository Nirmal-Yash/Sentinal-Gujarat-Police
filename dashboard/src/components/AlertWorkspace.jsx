import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { api } from '../api/client'
import { isValidPlateFilter, plateValidationMessage } from '../lib/validators'
import AlertStatusBadge from './alerts/AlertStatusBadge'
import AlertTypeBadge from './alerts/AlertTypeBadge'
import AlertDateFilter from './alerts/AlertDateFilter'
import { notifyToast } from './alerts/toast'
import { sortSightingsChronologically } from '../lib/routeSightings'
import { alertTimestamp, buildAlertQueryParams, canonicalAlertType } from '../lib/alertFilters'
import './alerts/alerts.css'

const STATUS_OPTIONS = ['ALL', 'NEW', 'ACKNOWLEDGED', 'INVESTIGATING', 'RESOLVED', 'CLOSED']
const PRIORITY_OPTIONS = ['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
const TYPE_OPTIONS = ['ALL', 'WATCHLIST_HIT', 'PLATE_SIGHTING', 'PERSON_MATCH', 'CROWD_ANOMALY', 'RUNNING_CROWD']
const SEVERITY_STYLES = {
  CRITICAL: { tone: '#FF3B30', border: 'rgba(255,59,48,.55)', glow: '0 0 0 1px rgba(255,59,48,.08)' },
  HIGH: { tone: '#FF3B30', border: 'rgba(255,59,48,.45)', glow: '0 0 0 1px rgba(255,59,48,.06)' },
  MEDIUM: { tone: '#FFB300', border: 'rgba(255,179,0,.35)', glow: '0 0 0 1px rgba(255,179,0,.05)' },
  LOW: { tone: '#34C759', border: 'rgba(52,199,89,.25)', glow: 'none' },
}
const SEVERITY_ORDER = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 }
const STATUS_ORDER = { NEW: 0, ACKNOWLEDGED: 1, INVESTIGATING: 2, RESOLVED: 3, CLOSED: 4 }

const severityFor = a => {
  const p = String(a?.priority || 'MEDIUM').toUpperCase()
  return SEVERITY_STYLES[p] ? p : 'MEDIUM'
}
const formatTime = alert => {
  const ts = alertTimestamp(alert)
  if (!ts) return '—'
  return new Date(ts).toLocaleString('en-IN', { hour12: false })
}
const entityLabel = alert => {
  const plate = alert?.details?.plate_text
  if (plate) return plate
  const name = alert?.details?.watchlist_name || alert?.details?.person_name
  if (name) return name
  const entity = alert?.details?.entity_type || alert?.entity_type
  return entity ? String(entity).replace(/_/g, ' ') : '—'
}
function ActionButton({ children, onClick, disabled = false }) {
  return (
    <motion.button
      type="button"
      whileTap={{ scale: 0.96 }}
      whileHover={{ y: -1 }}
      disabled={disabled}
      onClick={e => { e.stopPropagation(); onClick?.() }}
      style={{
        minHeight: 34, padding: '0 11px', border: '1px solid var(--accent-border)', borderRadius: 7,
        background: 'var(--accent-soft)', color: 'var(--accent-strong)', fontSize: 10, fontWeight: 850,
        cursor: disabled ? 'wait' : 'pointer', opacity: disabled ? 0.6 : 1,
      }}
    >
      {children}
    </motion.button>
  )
}

function EvidenceItem({ item }) {
  const [state, setState] = useState({ loading: true, url: null, sha: item.sha256 || '', verified: false, error: '' })
  useEffect(() => {
    let active = true
    api.getEvidenceSignedToken(item.id)
      .then(r => active && setState({ loading: false, url: `/api/evidence/${item.id}/content-signed?access_token=${encodeURIComponent(r.token)}`, sha: r.sha256 || item.sha256 || '', verified: false, error: '' }))
      .catch(e => active && setState({ loading: false, url: null, sha: item.sha256 || '', verified: false, error: e?.message || 'Evidence unavailable' }))
    return () => { active = false }
  }, [item.id, item.sha256])
  const verify = async () => {
    if (!state.url) return
    try {
      const r = await fetch(state.url)
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
      const bytes = await r.arrayBuffer()
      const digest = await crypto.subtle.digest('SHA-256', bytes)
      const actual = Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, '0')).join('')
      setState(s => ({ ...s, verified: !s.sha || actual.toLowerCase() === s.sha.toLowerCase(), actualSha: actual }))
    } catch (e) {
      setState(s => ({ ...s, error: e?.message || 'Integrity verification failed' }))
    }
  }
  if (state.loading) return <div className="alert-evidence-box">Loading evidence…</div>
  if (state.error) return <div className="alert-evidence-box alert-evidence-error">{state.error}</div>
  return (
    <div className="alert-evidence-card">
      <img src={state.url} alt="Alert evidence" onLoad={verify} onError={() => setState(s => ({ ...s, error: 'Evidence content unavailable', url: null }))} />
      <div className="alert-evidence-meta">
        <span>{item.media_type || 'Evidence'}</span>
        <span title={state.sha} style={{ fontFamily: 'monospace' }}>{state.sha ? `SHA256 ${state.sha.slice(0, 16)}…` : 'SHA256 not recorded'}</span>
      </div>
      <div className={state.verified ? 'alert-integrity-ok' : 'alert-integrity-pending'}>
        {state.verified ? '● SHA-256 verified' : '● Integrity pending verification'}
      </div>
    </div>
  )
}

function Evidence({ alert }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  useEffect(() => {
    let active = true
    const id = alert?.id || alert?.alert_id
    if (!id) return undefined
    setLoading(true)
    api.listEvidence({ alert_id: id, limit: 10 })
      .then(r => active && setItems(Array.isArray(r) ? r : []))
      .catch(() => active && setItems([]))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [alert?.id, alert?.alert_id])
  if (loading) return <div className="alert-evidence-box">Loading evidence…</div>
  if (!items.length) return null
  return (
    <section style={{ marginTop: 14 }}>
      <div className="alert-section-label">Evidence</div>
      <div style={{ display: 'grid', gap: 9 }}>{items.map(item => <EvidenceItem item={item} key={item.id} />)}</div>
    </section>
  )
}

const ALERT_OPERATE_ROLES = new Set(['OPERATOR', 'INVESTIGATOR', 'ADMIN', 'SUPERADMIN'])
const mergeCanonicalAlerts = items => {
  const map = new Map()
  ;(Array.isArray(items) ? items : []).forEach(item => {
    const id = String(item?.alert_id || item?.id || '')
    if (!id) return
    map.set(id, { ...(map.get(id) || {}), ...item })
  })
  return Array.from(map.values())
}

export default function AlertWorkspace({
  initialAlerts = [],
  onTransition,
  onOpenInvestigation,
  onLocateRoute,
  principal,
  testMode = false,
  testSession = null,
}) {
  const [alerts, setAlerts] = useState(mergeCanonicalAlerts(initialAlerts || []))
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(false)
  const [filters, setFilters] = useState({
    priority: 'ALL',
    status: 'ALL',
    alertType: 'ALL',
    camera: '',
    plate: '',
    date: { preset: 'ALL', from: '', to: '' },
  })
  const [plateError, setPlateError] = useState('')
  const [sort, setSort] = useState({ key: 'time', dir: 'desc' })
  const [routeLoading, setRouteLoading] = useState(false)
  const [showTechnical, setShowTechnical] = useState(false)
  const [actionPending, setActionPending] = useState(null)
  const [error, setError] = useState('')
  const controllerRef = useRef(null)
  const requestIdRef = useRef(0)

  const load = useCallback(async (silent = false) => {
    if (filters.plate && !isValidPlateFilter(filters.plate)) {
      setPlateError(plateValidationMessage(filters.plate) || 'Invalid plate filter')
      return
    }
    setPlateError('')
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    const rid = ++requestIdRef.current
    if (!silent) setLoading(true)
    setError('')
    const shared = buildAlertQueryParams(filters)
    try {
      const result = testMode && testSession?.id
        ? await api.getTestAlerts(testSession.id, shared, { signal: controller.signal })
        : await api.getAlerts(shared, { signal: controller.signal })
      if (!controller.signal.aborted && rid === requestIdRef.current) setAlerts(mergeCanonicalAlerts(result))
    } catch (e) {
      if (e?.name !== 'AbortError' && !controller.signal.aborted && rid === requestIdRef.current) {
        setError(e?.message || 'Failed to load alerts')
        if (!silent) notifyToast(e?.message || 'Failed to load alerts', 'error')
      }
    } finally {
      if (!controller.signal.aborted && rid === requestIdRef.current && !silent) setLoading(false)
    }
  }, [filters, testMode, testSession])

  useEffect(() => {
    load()
    const timer = setInterval(() => load(true), testMode ? 2500 : 15000)
    return () => {
      clearInterval(timer)
      controllerRef.current?.abort()
    }
  }, [load, testMode])

  const toggleSort = key => {
    setSort(current => current.key === key
      ? { key, dir: current.dir === 'asc' ? 'desc' : 'asc' }
      : { key, dir: key === 'time' ? 'desc' : 'asc' })
  }

  const sorted = useMemo(() => {
    const rows = [...alerts]
    const dir = sort.dir === 'asc' ? 1 : -1
    const compareId = (a, b) => String(a.id || a.alert_id || '').localeCompare(String(b.id || b.alert_id || ''))
    rows.sort((a, b) => {
      if (sort.key === 'time') {
        const delta = (alertTimestamp(a) - alertTimestamp(b)) * dir
        return delta !== 0 ? delta : compareId(a, b)
      }
      if (sort.key === 'severity') {
        const sa = SEVERITY_ORDER[severityFor(a)] ?? 9
        const sb = SEVERITY_ORDER[severityFor(b)] ?? 9
        const delta = (sa - sb) * dir
        return delta !== 0 ? delta : (alertTimestamp(b) - alertTimestamp(a))
      }
      if (sort.key === 'status') {
        const sa = STATUS_ORDER[String(a.status || 'NEW').toUpperCase()] ?? 9
        const sb = STATUS_ORDER[String(b.status || 'NEW').toUpperCase()] ?? 9
        const delta = (sa - sb) * dir
        return delta !== 0 ? delta : (alertTimestamp(b) - alertTimestamp(a))
      }
      if (sort.key === 'type') {
        const delta = canonicalAlertType(a.alert_type).localeCompare(canonicalAlertType(b.alert_type)) * dir
        return delta !== 0 ? delta : (alertTimestamp(b) - alertTimestamp(a))
      }
      return 0
    })
    return rows
  }, [alerts, sort])

  const transition = useCallback(async (alert, target) => {
    const id = alert.id || alert.alert_id
    if (!id) return
    setActionPending(`${id}:${target}`)
    try {
      await onTransition?.(alert, target)
      setAlerts(v => v.map(x => (x.id || x.alert_id) === id ? { ...x, status: target, acknowledged: target !== 'NEW' } : x))
      setSelected(v => v && (v.id || v.alert_id) === id ? { ...v, status: target, acknowledged: target !== 'NEW' } : v)
      notifyToast(`Alert ${target.toLowerCase()}.`, 'success')
    } catch (e) {
      notifyToast(e?.message || 'Alert action failed', 'error')
    } finally {
      setActionPending(null)
    }
  }, [onTransition])

  const viewRoute = useCallback(async alert => {
    const plate = alert?.details?.plate_text
    if (!plate || !onLocateRoute) return
    setRouteLoading(true)
    try {
      let sightings = []
      if (testMode && testSession) {
        const r = await api.getTestPlateJourney(testSession.id, plate)
        sightings = (r.sightings || []).filter(s => s.lat != null && s.lng != null)
      } else {
        const r = await api.searchPlateJourney(plate)
        sightings = (r.journeys || []).flatMap(j => j.sightings || []).filter(s => s.lat != null && s.lng != null)
      }
      if (!sightings.length) {
        const lat = alert.lat ?? alert.details?.lat
        const lng = alert.lng ?? alert.details?.lng
        if (lat != null && lng != null) {
          sightings = [{
            cam_name: alert.cam_name || alert.camera_label,
            lat,
            lng,
            timestamp: alert.created_at || alert.event_at,
          }]
        }
      }
      if (!sightings.length) {
        notifyToast('No GPS-located sightings found for this plate.', 'error')
        return
      }
      onLocateRoute(sortSightingsChronologically(sightings))
    } catch (e) {
      notifyToast(e?.message || 'Route lookup failed', 'error')
    } finally {
      setRouteLoading(false)
    }
  }, [onLocateRoute, testMode, testSession])

  const fresh = sorted.filter(a => (a.status || 'NEW') === 'NEW').length
  const critical = sorted.filter(a => severityFor(a) === 'CRITICAL').length
  const high = sorted.filter(a => ['CRITICAL', 'HIGH'].includes(severityFor(a))).length
  const sortMark = key => sort.key === key ? (sort.dir === 'asc' ? ' ↑' : ' ↓') : ''

  return (
    <div className="sentinel-alerts-page" style={{ height: '100%', width: '100%', minHeight: 0, display: 'flex', flexDirection: 'column', background: 'var(--bg)', color: 'var(--text)' }}>
      <header className="alerts-toolbar">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 850 }}>Alerts</h1>
            <span className="alerts-total">{sorted.length}</span>
          </div>
          <div className="alerts-subtitle">Operator queue · reasoning · lifecycle</div>
        </div>
        <div className="alerts-summary">
          {critical > 0 && <span className="summary-critical">{critical} Critical</span>}
          {high > 0 && <span className="summary-high">{high} High</span>}
          {fresh > 0 && <span className="summary-new">{fresh} New</span>}
          <ActionButton disabled={loading} onClick={() => load()}>{loading ? 'Refreshing…' : 'Refresh'}</ActionButton>
        </div>
        <div className="alerts-filters">
          <select value={filters.priority} onChange={e => setFilters(f => ({ ...f, priority: e.target.value }))}>
            {PRIORITY_OPTIONS.map(v => <option key={v}>{v}</option>)}
          </select>
          <select value={filters.status} onChange={e => setFilters(f => ({ ...f, status: e.target.value }))}>
            {STATUS_OPTIONS.map(v => <option key={v}>{v}</option>)}
          </select>
          <select value={filters.alertType} onChange={e => setFilters(f => ({ ...f, alertType: e.target.value }))}>
            {TYPE_OPTIONS.map(v => <option key={v} value={v}>{v === 'ALL' ? 'All types' : v.replace(/_/g, ' ')}</option>)}
          </select>
          <input value={filters.camera} onChange={e => setFilters(f => ({ ...f, camera: e.target.value }))} placeholder="Camera name" />
          <input
            value={filters.plate}
            onChange={e => { setFilters(f => ({ ...f, plate: e.target.value })); setPlateError('') }}
            placeholder="Plate"
            style={plateError ? { borderColor: 'rgba(255,59,48,.55)' } : undefined}
          />
          <AlertDateFilter value={filters.date} onChange={date => setFilters(f => ({ ...f, date }))} />
        </div>
        {plateError && <div className="alerts-error" style={{ gridColumn: '1 / -1' }}>{plateError}</div>}
      </header>
      {error && <div className="alerts-error">{error}</div>}
      <main style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: 12 }}>
        <div className="alerts-table">
          <div className="alerts-head">
            <span className="sortable" onClick={() => toggleSort('severity')}>Severity{sortMark('severity')}</span>
            <span className="sortable" onClick={() => toggleSort('type')}>Type{sortMark('type')}</span>
            <span>Plate / Entity</span>
            <span>Camera</span>
            <span>Reasoning</span>
            <span className="sortable" onClick={() => toggleSort('status')}>Status{sortMark('status')}</span>
            <span className="sortable" onClick={() => toggleSort('time')}>Time{sortMark('time')}</span>
          </div>
          <AnimatePresence initial={false} mode="popLayout">
            {sorted.map(alert => {
              const sev = SEVERITY_STYLES[severityFor(alert)]
              const camLabel = alert.cam_name || alert.camera_label || '—'
              const location = alert.location || alert.details?.location
              return (
                <motion.button
                  layout
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, x: -12 }}
                  transition={{ duration: 0.16 }}
                  key={alert.id || alert.alert_id}
                  onClick={() => { setSelected(alert); setShowTechnical(false) }}
                  className="alert-row"
                  style={{ borderLeftColor: sev.border, boxShadow: sev.glow }}
                >
                  <span style={{ color: sev.tone, fontWeight: 900, fontSize: 8 }}>{severityFor(alert)}</span>
                  <span><AlertTypeBadge type={alert.alert_type} compact /></span>
                  <span className="alert-entity">{entityLabel(alert)}</span>
                  <span className="alert-camera" title={location || ''}>{camLabel}{location ? ` · ${location}` : ''}</span>
                  <span className="alert-reasoning">{alert.human_summary || '—'}</span>
                  <span><AlertStatusBadge status={alert.status || 'NEW'} /></span>
                  <span className="alert-time">{formatTime(alert)}</span>
                </motion.button>
              )
            })}
          </AnimatePresence>
          {!sorted.length && <div className="alerts-empty">No alerts match the selected filters.</div>}
        </div>
      </main>
      <AnimatePresence>
        {selected && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="alert-drawer-overlay"
            onClick={e => e.target === e.currentTarget && setSelected(null)}
          >
            <motion.section initial={{ x: 30 }} animate={{ x: 0 }} exit={{ x: 30 }} className="alert-drawer">
              <header className="alert-drawer-header">
                <div>
                  <div className="alert-drawer-title">{String(selected.alert_type || 'Alert').replace(/_/g, ' ')}</div>
                  <div className="alerts-subtitle">
                    {selected.cam_name || selected.camera_label || 'Camera'} · {formatTime(selected)}
                  </div>
                </div>
                <button type="button" onClick={() => setSelected(null)} className="alert-close">×</button>
              </header>
              <div className="alert-drawer-body">
                <div style={{ display: 'flex', gap: 7, alignItems: 'center', flexWrap: 'wrap' }}>
                  <AlertStatusBadge status={selected.status || 'NEW'} />
                  <AlertTypeBadge type={selected.alert_type} />
                  <span style={{ fontSize: 9, fontWeight: 850 }}>Priority: {selected.priority || 'MEDIUM'}</span>
                </div>
                {selected.details?.plate_text && <div className="plate-highlight">{selected.details.plate_text}</div>}
                {selected.human_summary && (
                  <div className="alert-reasoning-block">{selected.human_summary}</div>
                )}
                <Evidence alert={selected} />
                <button type="button" className="alert-details-toggle" onClick={() => setShowTechnical(v => !v)}>
                  {showTechnical ? 'Hide technical details' : 'Show technical details'}
                </button>
                {showTechnical && (
                  <pre className="alert-details alert-details-collapsed">{JSON.stringify(selected.details || {}, null, 2)}</pre>
                )}
                <div className="alert-actions">
                  {ALERT_OPERATE_ROLES.has(principal?.role) && selected.status === 'NEW' && (
                    <ActionButton disabled={actionPending === `${selected.id}:ACKNOWLEDGED`} onClick={() => transition(selected, 'ACKNOWLEDGED')}>Acknowledge</ActionButton>
                  )}
                  {ALERT_OPERATE_ROLES.has(principal?.role) && selected.status === 'ACKNOWLEDGED' && (
                    <ActionButton disabled={actionPending === `${selected.id}:INVESTIGATING`} onClick={() => transition(selected, 'INVESTIGATING')}>Investigate</ActionButton>
                  )}
                  {ALERT_OPERATE_ROLES.has(principal?.role) && selected.status === 'INVESTIGATING' && (
                    <ActionButton disabled={actionPending === `${selected.id}:RESOLVED`} onClick={() => transition(selected, 'RESOLVED')}>Resolve</ActionButton>
                  )}
                  {ALERT_OPERATE_ROLES.has(principal?.role) && selected.status === 'RESOLVED' && (
                    <ActionButton disabled={actionPending === `${selected.id}:CLOSED`} onClick={() => transition(selected, 'CLOSED')}>Close</ActionButton>
                  )}
                  {selected.details?.plate_text && (
                    <ActionButton onClick={() => onOpenInvestigation?.({ tab: 'plate', query: selected.details.plate_text })}>Investigate Plate</ActionButton>
                  )}
                  {selected.details?.plate_text && onLocateRoute && (
                    <ActionButton disabled={routeLoading} onClick={() => viewRoute(selected)}>{routeLoading ? 'Loading Route…' : 'View Route on Map'}</ActionButton>
                  )}
                </div>
              </div>
            </motion.section>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
