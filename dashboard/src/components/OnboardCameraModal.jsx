import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { api } from '../api/client'

const GUJARAT = [22.4, 71.2]
const fields = [['name', 'Camera name', true], ['stream_id', 'Stream ID'], ['location', 'Location'], ['department', 'Department'], ['owner_organization', 'Owner'], ['rtsp_url', 'RTSP URL'], ['hls_url', 'HLS URL'], ['lat', 'Latitude'], ['lng', 'Longitude']]
const pinIcon = L.divIcon({ className: 'sentinel-onboard-pin', iconSize: [30, 38], iconAnchor: [15, 38], html: '<div style="width:30px;height:30px;border-radius:50% 50% 50% 0;background:#1f6feb;border:3px solid #fff;transform:rotate(-45deg);box-shadow:0 2px 8px rgba(0,0,0,.45)"><span style="display:block;width:9px;height:9px;border-radius:50%;background:#fff;margin:7px auto"></span></div>' })

export default function OnboardCameraModal({ onClose, onSaved, onImport }) {
  const mapNode = useRef(null), mapRef = useRef(null), markerRef = useRef(null)
  const [form, setForm] = useState({ name: '', stream_id: '', location: '', lat: '', lng: '', rtsp_url: '', hls_url: '', department: '', owner_organization: '', vendor_id: '', model_id: '' })
  const [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const [file, setFile] = useState(null), [importResult, setImportResult] = useState(null)
  const [vendors, setVendors] = useState([]), [models, setModels] = useState([])
  const setCoords = (lat, lng) => setForm(value => ({ ...value, lat: Number(lat).toFixed(6), lng: Number(lng).toFixed(6) }))

  useEffect(() => {
    const map = L.map(mapNode.current, { zoomControl: true }).setView(GUJARAT, 7)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: 'OpenStreetMap contributors' }).addTo(map)
    map.on('click', event => setCoords(event.latlng.lat, event.latlng.lng)); mapRef.current = map
    return () => map.remove()
  }, [])
  useEffect(() => { api.getVendors().then(setVendors).catch(() => setVendors([])) }, [])
  useEffect(() => {
    if (!form.vendor_id) { setModels([]); return }
    api.getVendorModels(form.vendor_id).then(setModels).catch(() => setModels([]))
  }, [form.vendor_id])
  useEffect(() => {
    const lat = Number(form.lat), lng = Number(form.lng), map = mapRef.current
    if (!map || !Number.isFinite(lat) || !Number.isFinite(lng)) return
    if (!markerRef.current) {
      markerRef.current = L.marker([lat, lng], { draggable: true, icon: pinIcon, title: 'Camera location' }).addTo(map)
      markerRef.current.on('dragend', event => { const point = event.target.getLatLng(); setCoords(point.lat, point.lng) })
    } else markerRef.current.setLatLng([lat, lng])
    map.panTo([lat, lng])
  }, [form.lat, form.lng])

  const change = event => setForm(value => ({ ...value, [event.target.name]: event.target.value }))
  const submit = async event => {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const body = { ...form, stream_id: form.stream_id ? Number(form.stream_id) : undefined, vendor_id: form.vendor_id || undefined, model_id: form.model_id || undefined, lat: form.lat === '' ? undefined : Number(form.lat), lng: form.lng === '' ? undefined : Number(form.lng), coord_source: form.lat !== '' && form.lng !== '' ? 'manual' : 'unknown', coord_confidence: form.lat !== '' && form.lng !== '' ? 1 : undefined }
      await onSaved(body); onClose()
    } catch (err) { setError(err.message || 'Unable to onboard camera') } finally { setBusy(false) }
  }
  const importCsv = async () => {
    if (!file) return
    setBusy(true); setError('')
    try { setImportResult(await onImport(file)) } catch (err) { setError(err.message || 'Unable to import CSV') } finally { setBusy(false) }
  }

  return <div onClick={event => event.target === event.currentTarget && onClose()} style={overlay}>
    <form onSubmit={submit} style={modal}>
      <header style={header}><b>Onboard camera</b><button type="button" onClick={onClose} style={close}>x</button></header>
      <section style={{ display: 'grid', gridTemplateColumns: 'minmax(300px, .9fr) minmax(360px, 1.1fr)', minHeight: 0, flex: 1 }}>
        <div style={{ padding: 14, overflowY: 'auto' }}>
          <div style={{ marginBottom: 14, paddingBottom: 12, borderBottom: '1px solid var(--border)' }}>
            <b style={{ fontSize: 12 }}>Bulk registry import</b>
            <label style={labelStyle}>Registry CSV or XLSX<input type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={event => setFile(event.target.files?.[0] || null)} style={input}/></label>
            <button type="button" disabled={busy || !file} onClick={importCsv} style={secondary}>Import and audit</button>
            <small style={{ display: 'block', marginTop: 5, color: 'var(--text2)' }}>Supports CSV/XLSX, common headers, and decimal or DMS coordinates. Invalid rows are retained in the audit history.</small>
            {importResult && <small style={{ display: 'block', marginTop: 5, color: importResult.rejected_rows ? 'var(--medium)' : 'var(--green)' }}>Imported {importResult.accepted_rows}/{importResult.total_rows}; rejected {importResult.rejected_rows}.</small>}
          </div>
          {fields.map(([name, label, required]) => <label key={name} style={labelStyle}>{label}<input name={name} value={form[name]} required={required} onChange={change} style={input}/></label>)}
          <label style={labelStyle}>Vendor<select name="vendor_id" value={form.vendor_id} onChange={event => { change(event); setForm(value => ({ ...value, model_id: '' })) }} style={input}><option value="">Unspecified</option>{vendors.map(vendor => <option key={vendor.id} value={vendor.id}>{vendor.name}</option>)}</select></label>
          <label style={labelStyle}>Camera model<select name="model_id" value={form.model_id} disabled={!form.vendor_id} onChange={change} style={input}><option value="">Unspecified</option>{models.map(model => <option key={model.id} value={model.id}>{model.name}</option>)}</select></label>
          <small style={{ color: 'var(--text2)' }}>Click the map or drag the pin; coordinates update both ways.</small>
          {error && <p style={{ color: 'var(--red)', fontSize: 12 }}>{error}</p>}
        </div>
        <div ref={mapNode} style={{ minHeight: 420, background: '#1a1f2e' }}/>
      </section>
      <footer style={{ padding: 12, display: 'flex', justifyContent: 'flex-end', gap: 8, borderTop: '1px solid var(--border)', background: 'var(--surface)' }}><button type="button" onClick={onClose} style={secondary}>Cancel</button><button type="submit" disabled={busy} style={primary}>{busy ? 'Saving...' : 'Save camera'}</button></footer>
    </form>
  </div>
}
const overlay = { position: 'fixed', inset: 0, zIndex: 3000, display: 'grid', placeItems: 'center', background: 'rgba(0,0,0,.7)' }
const modal = { width: 'min(980px,96vw)', height: 'min(780px,90vh)', display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 9 }
const header = { display: 'flex', justifyContent: 'space-between', padding: '12px 14px', borderBottom: '1px solid var(--border)' }
const close = { border: 0, background: 'transparent', color: 'var(--text)', cursor: 'pointer', fontSize: 20 }
const labelStyle = { display: 'grid', gap: 4, marginBottom: 9, fontSize: 11, color: 'var(--text2)' }
const input = { padding: '7px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--surface2)', color: 'var(--text)' }
const secondary = { padding: '7px 10px', borderRadius: 5, border: '1px solid var(--border)', background: 'transparent', color: 'var(--text)', cursor: 'pointer' }
const primary = { ...secondary, border: 0, background: 'var(--accent)', color: '#fff' }
