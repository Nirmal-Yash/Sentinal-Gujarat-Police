import { useEffect, useState } from 'react'
import { api } from '../api/client'

const MAX_VIDEO_SIZE_BYTES = 200 * 1024 * 1024
const TEST_SELECTION_KEY = 'sentinel.test.feed.selection.v1'
const TEST_ASSETS_KEY = 'sentinel.test.feed.assets.v1'
const readTestCache = key => { try { const raw = localStorage.getItem(key); return raw ? JSON.parse(raw) : [] } catch { return [] } }
const bytes = n => n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`

export default function TestDiagnosticsModal({ onClose, onStarted, manageOnly=false, testSessionId=null, onFeedAdded }) {
  const [assets, setAssets] = useState(() => readTestCache(TEST_ASSETS_KEY)), [selected, setSelected] = useState([]), [loop, setLoop] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState(''), [selectedFiles, setSelectedFiles] = useState([])
  useEffect(() => { api.getTestAssets().then(rows => { setAssets(rows); try { localStorage.setItem(TEST_ASSETS_KEY, JSON.stringify(rows)) } catch {} try { localStorage.setItem(TEST_ASSETS_KEY, JSON.stringify(rows)) } catch {} try { const saved=JSON.parse(localStorage.getItem(TEST_SELECTION_KEY)||'[]'); const valid=saved.filter(id=>rows.some(asset=>String(asset.id)===String(id))).slice(0,30); setSelected(valid.length?valid:rows.slice(0,8).map(asset=>asset.id)); } catch { setSelected(rows.slice(0,8).map(asset=>asset.id)) } }).catch(error => setError(error.message)) }, [])
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
      setAssets(current => { const next=[...uploaded,...current.filter(item=>!uploaded.some(asset=>asset.id===item.id))]; try { localStorage.setItem(TEST_ASSETS_KEY,JSON.stringify(next)) } catch {} return next })
      setSelected(current => { const next=[...new Set([...current,...uploaded.map(asset=>asset.id)])].slice(0,30); try { localStorage.setItem(TEST_SELECTION_KEY,JSON.stringify(next)) } catch {} return next })
      setSelectedFiles([])
    } catch (err) { setError(err.message || 'Video upload failed') } finally { setBusy(false) }
  }
  const toggle = id => setSelected(current => { const next=current.includes(id)?current.filter(value=>value!==id):[...current,id].slice(0,8); try { localStorage.setItem(TEST_SELECTION_KEY,JSON.stringify(next)) } catch {} return next })
  const addToLiveFeed = async asset => {
    if (!manageOnly || !testSessionId) return
    setBusy(true); setError('')
    try { const added = await api.addTestFeed(testSessionId,{asset_id:asset.id,loop}); onFeedAdded?.(added); setAssets(current => { const next=current.map(item => item.id===asset.id ? {...item,in_use:true} : item); try { localStorage.setItem(TEST_ASSETS_KEY,JSON.stringify(next)) } catch {} return next }) }
    catch (err) { setError(err.message || 'Could not add video to live Test Feed') }
    finally { setBusy(false) }
  }
  const removeAsset = async asset => {
        if (!window.confirm('Remove \u201c' + asset.display_name + '\u201d from Test Mode? This deletes the uploaded video permanently.')) return
    setBusy(true); setError('')
    try {
      await api.removeTestVideo(asset.id)
      setAssets(current => { const next=current.filter(item => item.id !== asset.id); try { localStorage.setItem(TEST_ASSETS_KEY,JSON.stringify(next)) } catch {} return next })
      setSelected(current => { const next=current.filter(id=>id!==asset.id); try { localStorage.setItem(TEST_SELECTION_KEY,JSON.stringify(next)) } catch {} return next })
    } catch (err) { setError(err.message || 'Video could not be removed') } finally { setBusy(false) }
  }
  const runDemo = async () => { setBusy(true); setError(''); try { const session=await api.seedDemoTestSession(); onStarted(session); onClose() } catch(err){ setError(err.message||'Could not load demo scenario') } finally { setBusy(false) } }
  const run = async () => {
    if (manageOnly || !selected.length) return
    setBusy(true); setError('')
    try {
      const session = await api.createTestSession({ name: `Video test ${new Date().toLocaleString('en-IN')}`, cameras: selected.map((asset_id, index) => ({ asset_id, camera_label: `Test Camera ${index + 1}`, loop })) })
      onStarted(session); onClose()
    } catch (err) { setError(err.message || 'Could not start test') } finally { setBusy(false) }
  }
  return (
    <div style={overlay} onClick={event => event.target === event.currentTarget && onClose()}>
      <section style={modal}>
        <header style={header}>
          <div>
            <b>{manageOnly ? 'Test Feed Videos' : 'Isolated video test mode'}</b>
            <small style={sub}>{manageOnly ? 'Existing Test Feed videos. Add new videos or remove unused videos.' : 'Select videos to create isolated Test Feeds. Production CCTV and data are unaffected.'}</small>
          </div>
          <button type="button" onClick={onClose} style={close} aria-label="Close">×</button>
        </header>
        <main style={{padding:16, overflowY:'auto', minHeight:0}}>
          <div style={uploadBox}>
            <b>Upload test video</b>
            <small>MP4, MKV, MOV, WebM, AVI or M4V · Maximum 200 MB per file.</small>
            <input type="file" accept="video/*,.mkv,.avi,.m4v" multiple disabled={busy} onChange={upload}/>
            {selectedFiles.map(file => (
              <div key={`${file.name}-${file.size}`} style={file.size > MAX_VIDEO_SIZE_BYTES ? invalidFile : validFile}>
                <span style={{overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}>{file.name}</span>
                <span style={{marginLeft:'auto', fontFamily:'ui-monospace,SFMono-Regular,Menlo,monospace'}}>{(file.size / 1024 / 1024).toFixed(1)} MB</span>
                {file.size > MAX_VIDEO_SIZE_BYTES && <span style={{color:'var(--red)',fontWeight:800}}>⚠ Exceeds limit</span>}
              </div>
            ))}
          </div>
          <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', margin:'14px 0 8px', gap:10}}>
            <b style={{fontSize:12}}>Available local videos</b>
            <label style={{fontSize:11,color:'var(--text2)'}}><input type="checkbox" checked={loop} onChange={event => setLoop(event.target.checked)}/> Loop feeds</label>
          </div>
          <div style={assetGrid}>
            {assets.map(asset => (
              <div key={asset.id} style={{...assetCard, borderColor:selected.includes(asset.id)?'var(--accent)':'var(--border)'}}>
                {!manageOnly && <input type="checkbox" checked={selected.includes(asset.id)} onChange={() => toggle(asset.id)} disabled={busy}/>} 
                <span style={{minWidth:0,flex:1}}>
                  <b style={{display:'block',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{asset.display_name}</b>
                  <small>Test Feed {asset.in_use ? '· In use by a test session' : ''} · {asset.width || '?'}×{asset.height || '?'} · {asset.fps ? `${Number(asset.fps).toFixed(1)} FPS` : 'FPS N/A'} · {bytes(asset.size_bytes || 0)}</small>
                </span>
                <span style={{display:'flex',gap:5,alignItems:'center',flex:'0 0 auto'}}>{manageOnly && testSessionId && !asset.in_use && <button type="button" onClick={() => addToLiveFeed(asset)} disabled={busy} style={addButton} aria-label={`Add ${asset.display_name} to live Test Feed`}>Add</button>}<button type="button" onClick={() => removeAsset(asset)} disabled={busy} style={removeButton} aria-label={`Remove ${asset.display_name}`}>{asset.in_use ? 'Remove (live)' : 'Remove'}</button></span>
              </div>
            ))}
          </div>
          {!assets.length && <p style={note}>No readable local video was found. Upload a test video to continue.</p>}
          {error && <p style={{color:'var(--red)',fontSize:12}} role="alert">{error}</p>}
        </main>
        <footer style={footer}>
          <span style={{marginRight:'auto',color:'var(--text2)',fontSize:11}}>{selected.length}/30 slots selected</span>
          <button type="button" onClick={onClose} style={secondary} disabled={busy}>Close</button>
          {!manageOnly && <><button type="button" disabled={busy} onClick={runDemo} style={primary}>{busy ? 'Loading…' : 'Load demo scenario'}</button><button type="button" disabled={busy || !selected.length} onClick={run} style={secondary}>{busy ? 'Starting…' : 'Run selected'}</button></>}
        </footer>
      </section>
    </div>
  )
}
const overlay = { position: 'fixed', inset: 0, zIndex: 3100, display: 'grid', placeItems: 'center', background: 'rgba(0,0,0,.72)' }
const modal = { width: 'min(760px,95vw)', maxHeight: '88vh', display: 'flex', flexDirection: 'column', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 9, overflow: 'hidden' }
const header = { display: 'flex', justifyContent: 'space-between', gap: 14, padding: '12px 14px', borderBottom: '1px solid var(--border)' }
const sub = { display: 'block', marginTop: 3, color: 'var(--text2)', fontSize: 11, fontWeight: 400 }
const close = { border: 0, background: 'transparent', color: 'var(--text)', cursor: 'pointer', fontSize: 22 }
const uploadBox = { display: 'grid', gap: 6, padding: 12, border: '1px dashed var(--accent)', borderRadius: 7, color: 'var(--text2)', fontSize: 11 }
const validFile = { display:'flex', gap:8, alignItems:'center', padding:'5px 7px', borderRadius:5, background:'rgba(34,197,94,.06)', border:'1px solid rgba(34,197,94,.14)' }
const invalidFile = { display:'flex', gap:8, alignItems:'center', padding:'5px 7px', borderRadius:5, background:'rgba(239,68,68,.06)', border:'1px solid rgba(239,68,68,.28)', color:'var(--text)' }
const assetGrid = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: 8, minWidth:0 }
const assetCard = { display: 'flex', gap: 8, padding: 9, border: '1px solid', borderRadius: 6, background: 'var(--surface2)', fontSize: 11, cursor: 'pointer' }
const note = { color: 'var(--text2)', fontSize: 12 }
const footer = { display: 'flex', gap: 8, alignItems: 'center', padding: 12, borderTop: '1px solid var(--border)' }
const secondary = { padding: '7px 10px', borderRadius: 5, border: '1px solid var(--border)', background: 'transparent', color: 'var(--text)', cursor: 'pointer' }
const primary = { ...secondary, border: 0, background: 'var(--accent)', color: '#fff' }

const removeButton = { flex:'0 0 auto', alignSelf:'center', padding:'6px 8px', borderRadius:5, border:'1px solid var(--border-strong)', background:'var(--surface)', color:'var(--text)', cursor:'pointer', fontSize:9, fontWeight:800 }
const protectedBadge = { flex:'0 0 auto', alignSelf:'center', padding:'4px 7px', borderRadius:5, border:'1px solid var(--border)', background:'var(--surface)', color:'var(--text2)', fontSize:9, fontWeight:700 }

const addButton = { flex:'0 0 auto', padding:'6px 8px', borderRadius:5, border:'1px solid var(--accent)', background:'var(--accent-soft)', color:'var(--text)', cursor:'pointer', fontSize:9, fontWeight:800 }
