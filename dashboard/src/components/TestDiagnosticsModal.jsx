import { useState } from 'react'
import { api } from '../api/client'

export default function TestDiagnosticsModal({ onClose }) {
  const [session, setSession] = useState(null), [plate, setPlate] = useState('TEST0001'), [status, setStatus] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const create = async () => { setBusy(true); setError(''); try { setSession(await api.createTestSession({ name: `Dashboard diagnostic ${new Date().toISOString()}` })) } catch (err) { setError(err.message) } finally { setBusy(false) } }
  const inject = async () => { if (!session) return; setBusy(true); setError(''); try { await api.injectTestEvent(session.id, { camera_label: 'dashboard-synthetic-only', detection_type: 'plate', plate_text: plate, confidence: .91, create_alert: true }); setStatus(await api.getTestStatus(session.id)) } catch (err) { setError(err.message) } finally { setBusy(false) } }
  const close = async () => { try { if (session) await api.closeTestSession(session.id) } finally { onClose() } }
  return <div style={overlay} onClick={event => event.target === event.currentTarget && close()}><section style={modal}><header style={header}><div><b>Isolated test diagnostics</b><small style={sub}>Writes only to test tables and test Redis streams.</small></div><button onClick={close} style={closeButton}>x</button></header><div style={{ padding: 16 }}><p style={note}>This does not access live feeds, production alerts, detections, or watchlists.</p>{!session ? <button disabled={busy} onClick={create} style={primary}>{busy ? 'Creating...' : 'Start isolated session'}</button> : <><div style={sessionStyle}>Session active: {session.id}</div><label style={label}>Synthetic plate<input value={plate} maxLength="100" onChange={event => setPlate(event.target.value.toUpperCase())} style={input}/></label><button disabled={busy || !plate} onClick={inject} style={primary}>{busy ? 'Injecting...' : 'Inject test plate event'}</button>{status && <div style={result}>Session results: {status.detections} detections, {status.alerts} alerts. Production data affected: No.</div>}</>}{error && <p style={{ color: 'var(--red)', fontSize: 12 }}>{error}</p>}</div><footer style={footer}><button onClick={close} style={secondary}>Close session</button></footer></section></div>
}
const overlay = { position: 'fixed', inset: 0, zIndex: 3100, display: 'grid', placeItems: 'center', background: 'rgba(0,0,0,.7)' }
const modal = { width: 'min(500px,94vw)', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 9, overflow: 'hidden' }
const header = { display: 'flex', justifyContent: 'space-between', padding: '12px 14px', borderBottom: '1px solid var(--border)' }
const sub = { display: 'block', marginTop: 3, color: 'var(--text2)', fontSize: 11, fontWeight: 400 }
const closeButton = { border: 0, background: 'transparent', color: 'var(--text)', cursor: 'pointer', fontSize: 20 }
const note = { marginTop: 0, color: 'var(--text2)', fontSize: 12, lineHeight: 1.5 }
const label = { display: 'grid', gap: 5, margin: '12px 0', fontSize: 11, color: 'var(--text2)' }
const input = { padding: '8px', borderRadius: 5, border: '1px solid var(--border)', background: 'var(--surface2)', color: 'var(--text)' }
const primary = { padding: '8px 11px', border: 0, borderRadius: 5, background: 'var(--accent)', color: '#fff', cursor: 'pointer' }
const secondary = { padding: '7px 10px', borderRadius: 5, border: '1px solid var(--border)', background: 'transparent', color: 'var(--text)', cursor: 'pointer' }
const footer = { display: 'flex', justifyContent: 'flex-end', padding: 12, borderTop: '1px solid var(--border)' }
const sessionStyle = { padding: 8, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', borderRadius: 4, background: 'var(--surface2)', color: 'var(--text2)', fontSize: 11 }
const result = { marginTop: 12, padding: 9, borderRadius: 5, background: 'rgba(63,185,80,.10)', border: '1px solid rgba(63,185,80,.3)', color: 'var(--green)', fontSize: 12 }
