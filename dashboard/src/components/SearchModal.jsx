import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'

const overlay = { position: 'fixed', inset: 0, background: 'rgba(0,0,0,.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }
const modal = { background: 'var(--surface)', borderRadius: 10, border: '1px solid var(--border)', width: 'min(650px,95vw)', maxHeight: '80vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }

export default function SearchModal({ onClose }) {
  const [tab, setTab] = useState('camera')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const controllerRef = useRef(null)
  const sequenceRef = useRef(0)

  useEffect(() => {
    const value = query.trim()
    controllerRef.current?.abort()
    if ((tab === 'camera' && value.length < 1) || (tab === 'plate' && value.length < 3)) { setResults(null); setLoading(false); setError(''); return }
    const controller = new AbortController(); controllerRef.current = controller
    const requestNumber = ++sequenceRef.current
    const timer = setTimeout(async () => {
      setLoading(true); setError('')
      try {
        const response = tab === 'camera' ? await api.searchCameras(value, { signal: controller.signal }) : await api.searchPlate(value, { signal: controller.signal })
        if (requestNumber === sequenceRef.current) setResults(response)
      } catch (e) {
        if (e.name !== 'AbortError' && requestNumber === sequenceRef.current) setError(e.message)
      } finally { if (requestNumber === sequenceRef.current) setLoading(false) }
    }, 250)
    return () => { clearTimeout(timer); controller.abort() }
  }, [query, tab])

  const switchTab = next => { setTab(next); setQuery(''); setResults(null); setError('') }
  return <div style={overlay} onClick={e => e.target === e.currentTarget && onClose()}>
    <div style={modal}>
      <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><span style={{ fontWeight: 700, fontSize: 15 }}>Search</span><button onClick={onClose} aria-label="Close search" style={{ background: 'none', border: 'none', color: 'var(--text2)', cursor: 'pointer', fontSize: 20 }}>×</button></div>
      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)' }}>{[['camera', 'Camera registry'], ['plate', 'License plate']].map(([key, label]) => <button key={key} onClick={() => switchTab(key)} style={{ flex: 1, padding: '9px 0', border: 'none', borderBottom: `2px solid ${tab === key ? 'var(--accent)' : 'transparent'}`, background: 'transparent', color: tab === key ? 'var(--accent)' : 'var(--text2)', cursor: 'pointer', fontSize: 13 }}>{label}</button>)}</div>
      <div style={{ padding: '14px 18px' }}><input autoFocus value={query} onChange={e => setQuery(e.target.value)} placeholder={tab === 'camera' ? 'Camera ID, name, department, location, status…' : 'e.g. GJ03AA1234'} style={{ width: '100%', boxSizing: 'border-box', padding: '8px 12px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--surface2)', color: 'var(--text)', fontSize: 13 }} /><div style={{ color: 'var(--text2)', fontSize: 10, marginTop: 6 }}>{loading ? 'Searching…' : tab === 'camera' ? 'Searches as you type' : 'Enter at least 3 characters'}</div></div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 18px 18px' }}>
        {error && <div style={{ color: 'var(--red)', fontSize: 13 }}>{error}</div>}
        {results && tab === 'camera' && (results.items.length ? results.items.map(c => <div key={c.id} style={{ padding: '9px 10px', marginBottom: 6, borderRadius: 6, background: 'var(--surface2)', border: '1px solid var(--border)', fontSize: 12 }}><b>CAM-{String(c.stream_id || '?').padStart(2, '0')} · {c.name}</b><br/><span style={{ color: 'var(--text2)' }}>{c.location || 'Location unknown'} · {c.department} · {(c.health_status || c.status).toUpperCase()}</span></div>) : <div style={{ color: 'var(--text2)', fontSize: 13 }}>No cameras found</div>)}
        {results && tab === 'plate' && <>{results.watchlist_hits?.length > 0 && <div style={{ marginBottom: 12, padding: 10, borderRadius: 6, background: 'var(--red)22', border: '1px solid var(--red)', fontSize: 12 }}><b style={{ color: 'var(--red)' }}>Watchlist match</b>{results.watchlist_hits.map(h => <div key={h.id}>{h.name} — {h.description}</div>)}</div>}{results.detections?.length ? results.detections.map(d => <div key={d.id} style={{ padding: '8px 10px', marginBottom: 6, borderRadius: 6, background: 'var(--surface2)', border: '1px solid var(--border)', fontSize: 12 }}><b>{d.plate_text}</b> — {d.cam_name}<span style={{ color: 'var(--text2)', marginLeft: 8 }}>{new Date(d.timestamp).toLocaleString()}</span></div>) : <div style={{ color: 'var(--text2)', fontSize: 13 }}>No sightings found</div>}</>}
      </div>
    </div>
  </div>
}
