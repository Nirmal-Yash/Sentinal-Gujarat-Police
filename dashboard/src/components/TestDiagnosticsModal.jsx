import { useEffect, useState } from 'react'
import { api } from '../api/client'

const MAX_VIDEO_SIZE_BYTES = 200 * 1024 * 1024
const bytes = n => n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`

export default function TestDiagnosticsModal({ onClose, onStarted }) {
  const [assets, setAssets] = useState([]), [selected, setSelected] = useState([]), [loop, setLoop] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState(''), [selectedFiles, setSelectedFiles] = useState([])
  useEffect(() => { api.getTestAssets().then(rows => { setAssets(rows); setSelected(rows.slice(0, 8).map(asset => asset.id)) }).catch(error => setError(error.message)) }, [])
  const upload = async event => {
    const files = Array.from(event.target.files || [])
    event.target.value = ''
    if (!files.length) return
    setSelectedFiles(files)
    const oversized = files.filter(file => file.size > MAX_VIDEO_SIZE_BYTES)
    if (oversized.length) {
      setError(`Files exceed 200 MB limit: ${oversized.map(file => `${file.name} (${(file.size / 1024 / 1024).toFixed(1)} MB)`).join(', ')}. Please compress or trim the video.`)
      return
    }
    setBusy(true); setError('')
    try {
      const uploaded = []
      for (const file of files) uploaded.push(await api.uploadTestVideo(file))
      setAssets(current => [...uploaded, ...current.filter(item => !uploaded.some(asset => asset.id === item.id))])
      setSelected(current => [...new Set([...current, ...uploaded.map(asset => asset.id)])].slice(0, 8))
      setSelectedFiles([])
    } catch (err) { setError(err.message || 'Video upload failed') } finally { setBusy(false) }
  }
  const toggle = id => setSelected(current => current.includes(id) ? current.filter(value => value !== id) : [...current, id].slice(0, 8))
  const run = async () => {
    if (!selected.length) return
    setBusy(true); setError('')
    try {
      const session = await api.createTestSession({ name: `Video test ${new Date().toLocaleString('en-IN')}`, cameras: selected.map((asset_id, index) => ({ asset_id, camera_label: `Test Camera ${index + 1}`, loop })) })
      onStarted(session); onClose()
    } catch (err) { setError(err.message || 'Could not start test') } finally { setBusy(false) }
  }
  return <div style={overlay} onClick={event => event.target === event.currentTarget && onClose()}><section style={modal}><header style={header}><div><b>Isolated video test mode</b><small style={sub}>Uses only test streams, tables, and MediaMTX paths. Production CCTV is never read.</small></div><button onClick={onClose} style={close}>×</button></header><main style={{ padding: 16, overflowY: 'auto' }}><div style={uploadBox}><b>Upload test video</b><small>MP4, MKV, MOV, WebM, AVI or M4V · Maximum 200 MB per file · FFmpeg probes resolution.</small><input type="file" accept="video/*,.mkv,.avi,.m4v" multiple disabled={busy} onChange={upload}/>{selectedFiles.map(file => <div key={`${file.name}-${file.size}`} style={file.size > MAX_VIDEO_SIZE_BYTES ? invalidFile : validFile}><span style={{overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{file.name}</span><span style={{marginLeft:'auto',fontFamily:'ui-monospace,SFMono-Regular,Menlo,monospace'}}>{(file.size / 1024 / 1024).toFixed(1)} MB</span>{file.size > MAX_VIDEO_SIZE_BYTES && <span style={{color:'var(--red)',fontWeight:800}}>⚠ Exceeds limit</span>}</div>)}</div><div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', margin: '14px 0 8px' }}><b style={{ fontSize: 12 }}>Available local videos</b><label style={{ fontSize: 11, color: 'var(--text2)' }}><input type="checkbox" checked={loop} onChange={event => setLoop(event.target.checked)}/> Loop feeds</label></div><div style={assetGrid}>{assets.map(asset => <label key={asset.id} style={{ ...assetCard, borderColor: selected.includes(asset.id) ? 'var(--accent)' : 'var(--border)' }}><input type="checkbox" checked={selected.includes(asset.id)} onChange={() => toggle(asset.id)}/><span><b>{asset.display_name}</b><small>{asset.source_kind} · {asset.width || '?'}×{asset.height || '?'} · {asset.fps ? `${Number(asset.fps).toFixed(1)} FPS` : 'FPS N/A'} · {bytes(asset.size_bytes || 0)}</small></span></label>)}</div>{!assets.length && <p style={note}>No readable local video was found. Upload a test video to continue.</p>}{error && <p style={{ color: 'var(--red)', fontSize: 12 }}>{error}</p>}</main><footer style={footer}><span style={{ marginRight: 'auto', color: 'var(--text2)', fontSize: 11 }}>{selected.length}/8 feeds selected</span><button onClick={onClose} style={secondary}>Cancel</button><button disabled={busy || !selected.length} onClick={run} style={primary}>{busy ? 'Starting…' : 'Run test'}</button></footer></section></div>
}
const overlay = { position: 'fixed', inset: 0, zIndex: 3100, display: 'grid', placeItems: 'center', background: 'rgba(0,0,0,.72)' }
const modal = { width: 'min(760px,95vw)', maxHeight: '88vh', display: 'flex', flexDirection: 'column', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 9, overflow: 'hidden' }
const header = { display: 'flex', justifyContent: 'space-between', gap: 14, padding: '12px 14px', borderBottom: '1px solid var(--border)' }
const sub = { display: 'block', marginTop: 3, color: 'var(--text2)', fontSize: 11, fontWeight: 400 }
const close = { border: 0, background: 'transparent', color: 'var(--text)', cursor: 'pointer', fontSize: 22 }
const uploadBox = { display: 'grid', gap: 6, padding: 12, border: '1px dashed var(--accent)', borderRadius: 7, color: 'var(--text2)', fontSize: 11 }
const validFile = { display:'flex', gap:8, alignItems:'center', padding:'5px 7px', borderRadius:5, background:'rgba(34,197,94,.06)', border:'1px solid rgba(34,197,94,.14)' }
const invalidFile = { display:'flex', gap:8, alignItems:'center', padding:'5px 7px', borderRadius:5, background:'rgba(239,68,68,.06)', border:'1px solid rgba(239,68,68,.28)', color:'var(--text)' }
const assetGrid = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(260px,1fr))', gap: 8 }
const assetCard = { display: 'flex', gap: 8, padding: 9, border: '1px solid', borderRadius: 6, background: 'var(--surface2)', fontSize: 11, cursor: 'pointer' }
const note = { color: 'var(--text2)', fontSize: 12 }
const footer = { display: 'flex', gap: 8, alignItems: 'center', padding: 12, borderTop: '1px solid var(--border)' }
const secondary = { padding: '7px 10px', borderRadius: 5, border: '1px solid var(--border)', background: 'transparent', color: 'var(--text)', cursor: 'pointer' }
const primary = { ...secondary, border: 0, background: 'var(--accent)', color: '#fff' }
