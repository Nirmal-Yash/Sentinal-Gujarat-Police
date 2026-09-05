import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'

const MAX_VIDEO_SIZE_BYTES = 200 * 1024 * 1024
const MAX_FEEDS = 8
const bytes = n => n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`

export default function TestFeedManager({ session, cameras = [], onClose, onChanged }) {
  const [assets, setAssets] = useState([])
  const [selected, setSelected] = useState('')
  const [loop, setLoop] = useState(true)
  const [label, setLabel] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const activeAssetIds = useMemo(() => new Set(
    cameras.filter(camera => camera?.is_test).map(camera => String(camera.asset_id || ''))
  ), [cameras])

  const refreshAssets = async () => {
    try {
      const rows=await api.getTestAssets()
      setAssets(rows)
      setSelected(current=>current && rows.some(asset=>String(asset.id)===String(current)) ? current : String(rows.find(asset=>!asset.in_use)?.id||''))
      setError('')
    } catch (err) {
      setError(err?.message || 'Could not load test videos')
    }
  }

  useEffect(() => { refreshAssets() }, [])

  const available = assets.filter(asset => !asset.in_use && !activeAssetIds.has(String(asset.id)))

  const upload = async event => {
    const files = Array.from(event.target.files || [])
    event.target.value = ''
    if (!files.length) return
    const oversized = files.filter(file => file.size > MAX_VIDEO_SIZE_BYTES)
    if (oversized.length) {
      setError(`Files exceed 200 MB: ${oversized.map(file => file.name).join(', ')}`)
      return
    }
    setBusy(true)
    setError('')
    try {
      const uploaded = []
      for (const file of files) uploaded.push(await api.uploadTestVideo(file))
      setAssets(current => [...uploaded, ...current.filter(item => !uploaded.some(asset => asset.id === item.id))])
      if (!selected && uploaded[0]) setSelected(String(uploaded[0].id))
    } catch (err) {
      setError(err?.message || 'Video upload failed')
    } finally {
      setBusy(false)
    }
  }

  const add = async () => {
    if (!session?.id || !selected) return
    if (cameras.filter(camera => camera?.is_test).length >= MAX_FEEDS) {
      setError(`A Test Mode session can contain at most ${MAX_FEEDS} live feeds.`)
      return
    }
    setBusy(true)
    setError('')
    try {
      await api.addTestFeed(session.id, {
        asset_id: selected,
        camera_label: label.trim(),
        loop,
      })
      setLabel('')
      await onChanged?.()
      await refreshAssets()
    } catch (err) {
      setError(err?.message || 'Could not add test feed')
    } finally {
      setBusy(false)
    }
  }

  const removeAsset = async asset => {
    if (!asset?.id || !window.confirm(`Permanently remove “${asset.display_name}” from Test Assets? This cannot affect production CCTV.`)) return
    setBusy(true)
    setError('')
    try {
      await api.removeTestVideo(asset.id)
      await refreshAssets()
      await onChanged?.()
    } catch (err) {
      setError(err?.message || 'Could not remove test video')
    } finally {
      setBusy(false)
    }
  }

  return <div style={overlay} onClick={event => event.target === event.currentTarget && onClose()}>
    <section style={modal} aria-label="Test Feed manager">
      <header style={header}>
        <div>
          <b>Manage Test Feeds</b>
          <small style={sub}>{cameras.filter(camera => camera?.is_test).length}/{MAX_FEEDS} live feeds · Production CCTV remains isolated</small>
        </div>
        <button type="button" onClick={onClose} style={close} aria-label="Close Test Feed manager">×</button>
      </header>
      <main style={main}>
        <section style={panel}>
          <div style={row}><b>Add video to live Test Mode</b><span style={hint}>Only assets not already running in this session are listed.</span></div>
          <select value={selected} onChange={event => setSelected(event.target.value)} disabled={busy || !available.length} style={input}>
            <option value="">{available.length ? 'Select a test video…' : 'No additional test videos available'}</option>
            {available.map(asset => <option key={asset.id} value={asset.id}>{asset.display_name} · {asset.width || '?'}×{asset.height || '?'} · {asset.fps ? Number(asset.fps).toFixed(1)+' FPS' : 'FPS N/A'} · {bytes(asset.size_bytes || 0)}</option>)}
          </select>
          <div style={twoCol}>
            <input value={label} onChange={event => setLabel(event.target.value)} maxLength={255} placeholder="Optional camera label" disabled={busy} style={input}/>
            <label style={check}><input type="checkbox" checked={loop} onChange={event => setLoop(event.target.checked)} disabled={busy}/> Loop video</label>
          </div>
          <div style={row}><label style={uploadLabel}>Upload test video <input type="file" accept="video/*,.mkv,.avi,.m4v" multiple disabled={busy} onChange={upload}/></label><button type="button" onClick={add} disabled={busy || !selected || cameras.filter(camera => camera?.is_test).length >= MAX_FEEDS} style={primary}>{busy ? 'Working…' : '+ Add Live Feed'}</button></div>
        </section>
        <section>
          <div style={{...row, marginBottom:8}}><b>Test asset library</b><span style={hint}>{assets.length} asset{assets.length===1?'':'s'}</span></div>
          <div style={assetGrid}>{assets.map(asset => <article key={asset.id} style={assetCard}><div style={{minWidth:0,flex:1}}><b>{asset.display_name}</b><small>{asset.source_kind} · {asset.width || '?'}×{asset.height || '?'} · {asset.fps ? Number(asset.fps).toFixed(1)+' FPS' : 'FPS N/A'} · {bytes(asset.size_bytes || 0)}</small></div><button type="button" onClick={() => removeAsset(asset)} disabled={busy} style={danger}>Delete</button></article>)}</div>
        </section>
        {error && <p role="alert" style={{color:'var(--red)',fontSize:11,margin:0}}>{error}</p>}
      </main>
      <footer style={footer}><span style={hint}>Changes apply only to the active isolated Test session.</span><button type="button" onClick={onClose} style={secondary}>Done</button></footer>
    </section>
  </div>
}
const overlay={position:'fixed',inset:0,zIndex:3200,display:'grid',placeItems:'center',padding:16,background:'rgba(0,0,0,.78)'}
const modal={width:'min(820px,95vw)',maxHeight:'88vh',display:'flex',flexDirection:'column',background:'var(--surface)',border:'1px solid var(--border)',borderRadius:10,overflow:'hidden',boxShadow:'0 30px 90px rgba(0,0,0,.75)'}
const header={display:'flex',justifyContent:'space-between',gap:14,padding:'13px 15px',borderBottom:'1px solid var(--border)',background:'var(--surface2)'}
const sub={display:'block',marginTop:3,color:'var(--text2)',fontSize:10,fontWeight:400}
const close={border:0,background:'transparent',color:'var(--text)',cursor:'pointer',fontSize:22}
const main={display:'grid',gap:16,padding:15,overflowY:'auto'}
const panel={display:'grid',gap:9,padding:12,border:'1px solid var(--border)',borderRadius:8,background:'var(--surface2)'}
const row={display:'flex',alignItems:'center',gap:10}
const hint={color:'var(--text2)',fontSize:10}
const input={width:'100%',boxSizing:'border-box',padding:'8px 9px',border:'1px solid var(--border)',borderRadius:6,background:'var(--bg)',color:'var(--text)',fontSize:11}
const twoCol={display:'grid',gridTemplateColumns:'minmax(0,1fr) auto',gap:8,alignItems:'center'}
const check={display:'inline-flex',alignItems:'center',gap:5,color:'var(--text2)',fontSize:11,whiteSpace:'nowrap'}
const uploadLabel={display:'inline-flex',alignItems:'center',gap:7,color:'var(--accent)',fontSize:10,fontWeight:800}
const primary={padding:'7px 10px',border:0,borderRadius:5,background:'var(--accent)',color:'#fff',cursor:'pointer',fontSize:10,fontWeight:800}
const secondary={padding:'7px 10px',border:'1px solid var(--border)',borderRadius:5,background:'transparent',color:'var(--text)',cursor:'pointer',fontSize:10}
const danger={padding:'5px 8px',border:'1px solid rgba(239,68,68,.45)',borderRadius:5,background:'rgba(75,0,0,.24)',color:'var(--red)',cursor:'pointer',fontSize:9,fontWeight:800}
const assetGrid={display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(280px,1fr))',gap:8}
const assetCard={display:'flex',alignItems:'center',gap:10,padding:9,border:'1px solid var(--border)',borderRadius:7,background:'var(--surface2)'}
