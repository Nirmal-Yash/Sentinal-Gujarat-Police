import { useEffect, useState } from 'react'
import { api } from '../api/client'

export default function VendorModal({ onClose }) {
  const [vendors, setVendors] = useState([]), [selected, setSelected] = useState(null), [models, setModels] = useState([])
  const [vendorName, setVendorName] = useState(''), [modelName, setModelName] = useState(''), [error, setError] = useState('')
  const load = () => api.getVendors().then(setVendors).catch(err => setError(err.message))
  useEffect(load, [])
  useEffect(() => { if (selected) api.getVendorModels(selected.id).then(setModels).catch(err => setError(err.message)); else setModels([]) }, [selected])
  const addVendor = async event => { event.preventDefault(); setError(''); try { const vendor = await api.createVendor({ name: vendorName, protocol_support: ['RTSP'] }); setVendorName(''); await load(); setSelected(vendor) } catch (err) { setError(err.message) } }
  const addModel = async event => { event.preventDefault(); if (!selected) return; setError(''); try { await api.createVendorModel(selected.id, { name: modelName }); setModelName(''); setModels(await api.getVendorModels(selected.id)) } catch (err) { setError(err.message) } }
  return <div style={overlay} onClick={event => event.target === event.currentTarget && onClose()}><section style={modal}><header style={header}><b>Vendors and camera models</b><button onClick={onClose} style={close}>x</button></header><div style={body}><aside style={sidebar}>{vendors.map(vendor => <button key={vendor.id} onClick={() => setSelected(vendor)} style={{ ...item, background: selected?.id === vendor.id ? 'var(--surface2)' : 'transparent' }}>{vendor.name}</button>)}<form onSubmit={addVendor} style={form}><input value={vendorName} onChange={event => setVendorName(event.target.value)} placeholder="New vendor name" required style={input}/><button style={primary}>Add vendor</button></form></aside><main style={{ padding: 14 }}><b style={{ fontSize: 13 }}>{selected ? selected.name : 'Select a vendor'}</b>{selected && <><div style={{ margin: '10px 0', fontSize: 11, color: 'var(--text2)' }}>Protocols: {(selected.protocol_support || []).join(', ')}</div>{models.map(model => <div key={model.id} style={{ fontSize: 12, padding: '6px 0', borderBottom: '1px solid var(--border)' }}>{model.name} <span style={{ color: 'var(--text2)' }}>({model.camera_type})</span></div>)}<form onSubmit={addModel} style={{ ...form, marginTop: 14 }}><input value={modelName} onChange={event => setModelName(event.target.value)} placeholder="Camera model" required style={input}/><button style={primary}>Add model</button></form></>}{error && <p style={{ color: 'var(--red)', fontSize: 12 }}>{error}</p>}</main></div></section></div>
}
const overlay = { position: 'fixed', inset: 0, zIndex: 3000, display: 'grid', placeItems: 'center', background: 'rgba(0,0,0,.7)' }
const modal = { width: 'min(720px,94vw)', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 9 }
const header = { display: 'flex', justifyContent: 'space-between', padding: '12px 14px', borderBottom: '1px solid var(--border)' }
const close = { border: 0, background: 'transparent', color: 'var(--text)', cursor: 'pointer', fontSize: 20 }
const body = { display: 'grid', gridTemplateColumns: '230px 1fr', minHeight: 300 }
const sidebar = { padding: 10, borderRight: '1px solid var(--border)' }
const item = { width: '100%', textAlign: 'left', padding: 8, color: 'var(--text)', border: 0, borderRadius: 4, cursor: 'pointer' }
const form = { display: 'grid', gap: 7, marginTop: 10 }
const input = { padding: '7px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--surface2)', color: 'var(--text)' }
const primary = { padding: '7px 10px', borderRadius: 5, border: 0, background: 'var(--accent)', color: '#fff', cursor: 'pointer' }
