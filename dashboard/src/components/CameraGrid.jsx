import { useState, useEffect, useRef, useCallback, memo } from 'react'
import Hls from 'hls.js'

const streamMetadata = cam => {
  const width = cam.effective_width ?? cam.width, height = cam.effective_height ?? cam.height, fps = cam.effective_fps ?? cam.fps
  const values = []
  if (cam.effective_codec || cam.codec) values.push(cam.effective_codec || cam.codec)
  if (Number(width) > 0 && Number(height) > 0) values.push(`${width} x ${height}`)
  if (Number(fps) > 0) values.push(`${Number(fps).toFixed(1)} FPS`)
  return values.join(' · ') || 'Stream metadata unavailable'
}
const streamAspect = cam => {
  const width = Number(cam.effective_width ?? cam.width), height = Number(cam.effective_height ?? cam.height)
  return width > 0 && height > 0 ? width / height : 16 / 9
}
const CamIcon = ({ size = 14, color = 'currentColor' }) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M15 10l4.553-2.069A1 1 0 0121 8.82v6.36a1 1 0 01-1.447.893L15 14"/><rect x="1" y="6" width="15" height="12" rx="2"/></svg>
const MapPinIcon = ({ size = 14 }) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 10c0 5-8 12-8 12S4 15 4 10a8 8 0 1116 0Z"/><circle cx="12" cy="10" r="2.5"/></svg>
const ExpandIcon = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M8 3H3v5M16 3h5v5M21 16v5h-5M3 16v5h5"/></svg>
const CloseIcon = () => <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="m18 6-12 12M6 6l12 12"/></svg>
const GridIcon = ({ n }) => <svg width="14" height="14" viewBox="0 0 12 12" fill="currentColor">{n === 2 && <><rect width="5" height="12" rx="1"/><rect x="7" width="5" height="12" rx="1"/></>}{n === 3 && <><rect width="3" height="12" rx="1"/><rect x="4.5" width="3" height="12" rx="1"/><rect x="9" width="3" height="12" rx="1"/></>}{n === 4 && [0, 3.2, 6.3, 9.5].flatMap(x => [0, 6.5].map(y => <rect key={`${x}-${y}`} x={x} y={y} width="2.5" height="5.5" rx=".5"/>))}{n === 5 && [0, 2.5, 5, 7.5, 10].flatMap(x => [0, 6.5].map(y => <rect key={`${x}-${y}`} x={x} y={y} width="2" height="5.5" rx=".5"/>))}</svg>

// Playback uses canonical registry HLS, then its canonical browser MP4 fallback,
// then the locally cached frame.
function LivePlayer({ cam, muted = true, onLiveStatus, onAspectChange, fit = 'contain' }) {
  const videoRef = useRef(null), hlsRef = useRef(null), timerRef = useRef(null)
  const [mode, setMode] = useState(cam.hls_url ? 'hls' : 'snapshot')
  const [snapshot, setSnapshot] = useState(null), [live, setLive] = useState(false)
  const snapshotUrl = `/api/cameras/${cam.id}/snapshot`
  const advance = useCallback(from => { setMode(from === 'hls' && cam.stream_url ? 'stream' : from === 'stream' ? 'snapshot' : 'error'); setLive(false) }, [cam.stream_url])
  useEffect(() => { onLiveStatus?.(live) }, [live, onLiveStatus])
  useEffect(() => { hlsRef.current?.destroy(); clearInterval(timerRef.current); setMode(cam.hls_url ? 'hls' : cam.stream_url ? 'stream' : 'snapshot'); setSnapshot(null); setLive(false) }, [cam.id, cam.hls_url, cam.stream_url])
  useEffect(() => {
    if (mode !== 'hls') return
    if (!cam.hls_url) { advance('hls'); return }
    const video = videoRef.current
    const fallbackTimer = setTimeout(() => advance('hls'), 8000)
    if (Hls.isSupported()) {
      const hls = new Hls({ enableWorker: true, lowLatencyMode: true, backBufferLength: 6 })
      hls.loadSource(cam.hls_url); hls.attachMedia(video)
      hls.on(Hls.Events.MANIFEST_PARSED, () => clearTimeout(fallbackTimer))
      hls.on(Hls.Events.ERROR, (_, detail) => { if (detail.fatal) { clearTimeout(fallbackTimer); hls.destroy(); advance('hls') } })
      hlsRef.current = hls
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) video.src = cam.hls_url
    else advance('hls')
    return () => { clearTimeout(fallbackTimer); hlsRef.current?.destroy(); hlsRef.current = null }
  }, [mode, cam.hls_url, advance])
  useEffect(() => {
    if (mode !== 'stream' || !cam.stream_url) return
    const video = videoRef.current
    const token = cam.is_test ? localStorage.getItem('sentinel.jwt') : null
    const streamUrl = token ? `${cam.stream_url}${cam.stream_url.includes('?') ? '&' : '?'}access_token=${encodeURIComponent(token)}` : cam.stream_url
    video.src = streamUrl
    const failed = () => advance('stream')
    const fallbackTimer = setTimeout(failed, 12000)
    video.addEventListener('error', failed)
    video.addEventListener('playing', () => clearTimeout(fallbackTimer), { once: true })
    video.play().catch(() => {})
    return () => { clearTimeout(fallbackTimer); video.removeEventListener('error', failed); video.removeAttribute('src'); video.load() }
  }, [mode, cam.stream_url, advance])
  useEffect(() => {
    if (mode !== 'snapshot') return
    const load = () => setSnapshot(`${snapshotUrl}?t=${Date.now()}`)
    load(); timerRef.current = setInterval(load, 2500)
    return () => clearInterval(timerRef.current)
  }, [mode, snapshotUrl])
  const updateAspect = event => { const { videoWidth, videoHeight, naturalWidth, naturalHeight } = event.currentTarget; const w = videoWidth || naturalWidth, h = videoHeight || naturalHeight; if (w && h) onAspectChange?.(w / h) }
  return <div style={{ position: 'absolute', inset: 0, background: '#000' }}>
    <video ref={videoRef} autoPlay muted={muted} playsInline loop={cam.is_test} onPlaying={() => setLive(true)} onWaiting={() => setLive(false)} onLoadedMetadata={updateAspect} style={{ position: 'absolute', inset: 0, display: mode === 'hls' || mode === 'stream' ? 'block' : 'none', width: '100%', height: '100%', objectFit: fit }}/>
    {mode === 'snapshot' && snapshot && (
      <img src={snapshot} alt="Latest camera frame" onLoad={event => { setLive(true); updateAspect(event) }} onError={() => { setLive(false); advance('snapshot') }} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: fit }}/>
    )}
    {(mode === 'error' || (mode === 'snapshot' && !snapshot)) && <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', color: 'var(--text2)', fontSize: 11 }}>Feed unavailable</div>}
    {(mode === 'hls' || mode === 'stream') && !live && <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', background: 'rgba(0,0,0,.45)', color: 'rgba(255,255,255,.65)', fontSize: 10 }}>Connecting</div>}
    {live && <span style={{ position: 'absolute', right: 8, bottom: 6, color: '#fff', fontSize: 9, letterSpacing: .5 }}><i style={{ display: 'inline-block', width: 5, height: 5, marginRight: 3, borderRadius: '50%', background: '#f85149' }}/>LIVE</span>}
  </div>
}

const iconButton = { width: 30, height: 30, display: 'grid', placeItems: 'center', background: 'rgba(88,166,255,.12)', border: '1px solid var(--accent)', borderRadius: 6, color: 'var(--accent)', cursor: 'pointer', padding: 0 }
const hoverIconButton = { width: 25, height: 25, display: 'grid', placeItems: 'center', border: '1px solid rgba(255,255,255,.35)', borderRadius: 4, background: 'rgba(0,0,0,.7)', color: '#fff', cursor: 'pointer', padding: 0 }
function PlateOverlay({ analytics, cam }) {
  const box = analytics?.bbox || {}, width = Number(cam.effective_width || cam.width), height = Number(cam.effective_height || cam.height)
  const x1 = Number(box.x1), y1 = Number(box.y1), x2 = Number(box.x2), y2 = Number(box.y2)
  if (!analytics?.plate_text || !width || !height || !Number.isFinite(x1 + y1 + x2 + y2) || x2 <= x1 || y2 <= y1) return null
  const left = Math.max(0, Math.min(100, x1 / width * 100)), top = Math.max(0, Math.min(100, y1 / height * 100))
  const boxWidth = Math.max(1, Math.min(100 - left, (x2 - x1) / width * 100)), boxHeight = Math.max(1, Math.min(100 - top, (y2 - y1) / height * 100))
  return <div style={{ position: 'absolute', left: `${left}%`, top: `${top}%`, width: `${boxWidth}%`, height: `${boxHeight}%`, boxSizing: 'border-box', border: '2px solid #58a6ff', pointerEvents: 'none' }}><span style={{ position: 'absolute', left: -2, bottom: '100%', padding: '3px 5px', borderRadius: '3px 3px 0 0', background: '#58a6ff', color: '#071222', fontSize: 10, fontWeight: 800, lineHeight: 1, whiteSpace: 'nowrap' }}>{analytics.plate_text}</span></div>
}
function PlateBadge({ analytics }) {
  const box = analytics?.bbox || {}, width = Number(analytics?.width), height = Number(analytics?.height)
  const x1 = Number(box.x1), y1 = Number(box.y1), x2 = Number(box.x2), y2 = Number(box.y2)
  if (!analytics?.plate_text || !width || !height || !Number.isFinite(x1 + y1 + x2 + y2) || x2 <= x1 || y2 <= y1) return null
  const left = Math.max(0, Math.min(100, x1 / width * 100)), top = Math.max(0, Math.min(100, y1 / height * 100))
  return <div style={{ position: 'absolute', left: `${left}%`, top: `${top}%`, border: '2px solid #58a6ff', pointerEvents: 'none' }}><span style={{ position: 'absolute', left: -2, bottom: '100%', padding: '3px 5px', borderRadius: '3px 3px 0 0', background: '#58a6ff', color: '#071222', fontSize: 10, fontWeight: 800, lineHeight: 1, whiteSpace: 'nowrap' }}>{analytics.plate_text}</span></div>
}

function FullscreenModal({ cam, alertCount, analytics, onClose, onLocate }) {
  const [aspect, setAspect] = useState(() => streamAspect(cam)), padded = String(cam.stream_id || '?').padStart(2, '0')
  useEffect(() => setAspect(streamAspect(cam)), [cam])
  useEffect(() => { const key = event => { if (event.key === 'Escape') onClose() }; window.addEventListener('keydown', key); return () => window.removeEventListener('keydown', key) }, [onClose])
  useEffect(() => { document.body.style.overflow = 'hidden'; return () => { document.body.style.overflow = '' } }, [])
  return <div onClick={event => event.target === event.currentTarget && onClose()} style={{ position: 'fixed', inset: 0, zIndex: 2000, background: 'rgba(0,0,0,.88)', display: 'grid', placeItems: 'center', padding: 16 }}><section style={{ '--feed-aspect': aspect, width: 'min(92vw, calc(78vh * var(--feed-aspect)))', minWidth: 'min(92vw, 360px)', maxWidth: 1440, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden', boxShadow: '0 32px 96px rgba(0,0,0,.8)' }}><header style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', background: 'var(--surface2)', borderBottom: '1px solid var(--border)' }}><CamIcon size={16} color="var(--accent)"/><b style={{ fontSize: 14 }}>CAM-{padded}</b><span style={{ color: 'var(--text2)', fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{cam.name}</span><div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 7 }}>{alertCount > 0 && <span style={{ background: 'var(--high)', color: '#fff', borderRadius: 4, fontSize: 10, fontWeight: 700, padding: '2px 6px' }}>{alertCount} alerts</span>}<button onClick={() => onLocate(cam)} title="Locate on map" aria-label="Locate on map" style={iconButton}><MapPinIcon/></button><button onClick={onClose} title="Close live feed" aria-label="Close live feed" style={iconButton}><CloseIcon/></button></div></header><div style={{ position: 'relative', width: '100%', aspectRatio: aspect, maxHeight: '78vh', background: '#000' }}><LivePlayer cam={cam} muted={false} fit="contain" onAspectChange={setAspect}/><PlateOverlay analytics={analytics} cam={cam}/></div><footer style={{ display: 'flex', justifyContent: 'space-between', gap: 10, padding: '7px 14px', background: 'var(--surface2)', borderTop: '1px solid var(--border)', color: 'var(--text2)', fontSize: 11 }}><span>{cam.location || 'Location not registered'}</span><span>{streamMetadata(cam)} · Esc to close</span></footer></section></div>
}

const CameraCard = memo(function CameraCard({ cam, alertCount, analytics, onFocus, onLocate, animDelay }) {
  const [isLive, setIsLive] = useState(false), [aspect, setAspect] = useState(() => streamAspect(cam))
  const padded = String(cam.stream_id || '?').padStart(2, '0'), health = cam.health_status || cam.status || 'unknown'
  useEffect(() => setAspect(streamAspect(cam)), [cam])
  return <article className="camera-card" onClick={() => onFocus(cam)} style={{ background: 'var(--surface2)', borderRadius: 8, overflow: 'hidden', border: `1px solid ${alertCount ? 'var(--high)' : 'var(--border)'}`, display: 'flex', flexDirection: 'column', cursor: 'pointer', transition: 'border .2s, transform .15s', animation: `cardIn .22s ease ${animDelay}ms both` }} onMouseEnter={event => { event.currentTarget.style.transform = 'translateY(-2px)' }} onMouseLeave={event => { event.currentTarget.style.transform = 'translateY(0)' }}><div style={{ position: 'relative', aspectRatio: aspect, background: '#000' }}><LivePlayer cam={cam} muted onLiveStatus={setIsLive} onAspectChange={setAspect}/><div style={{ position: 'absolute', inset: '0 0 auto', padding: '6px 8px', display: 'flex', alignItems: 'center', gap: 6, pointerEvents: 'none', background: 'linear-gradient(rgba(0,0,0,.72),transparent)' }}><span style={{ color: 'rgba(255,255,255,.6)', fontWeight: 700, fontSize: 10 }}>CAM-{padded}</span><span style={{ color: 'rgba(255,255,255,.9)', fontSize: 10, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>{cam.name}</span><i style={{ marginLeft: 'auto', width: 6, height: 6, borderRadius: '50%', background: isLive ? 'var(--green)' : health === 'offline' ? 'var(--red)' : 'var(--yellow)' }}/></div>{alertCount > 0 && <span style={{ position: 'absolute', top: 6, right: 10, background: 'var(--high)', color: '#fff', borderRadius: 4, fontSize: 9, fontWeight: 700, padding: '1px 5px' }}>{alertCount}</span>}{analytics?.plate_text && <PlateBadge analytics={analytics}/>}<div className="camera-actions" style={{ position: 'absolute', right: 6, bottom: 5, display: 'flex', gap: 4, opacity: 0, transform: 'translateY(3px)', transition: 'opacity .15s, transform .15s' }}><button onClick={event => { event.stopPropagation(); onFocus(cam) }} title="View live feed" aria-label="View live feed" style={hoverIconButton}><ExpandIcon/></button><button onClick={event => { event.stopPropagation(); onLocate(cam) }} title="Locate on map" aria-label="Locate on map" style={{ ...hoverIconButton, color: '#9ecbff', borderColor: 'rgba(88,166,255,.8)' }}><MapPinIcon/></button></div><span style={{ position: 'absolute', left: 7, bottom: 5, color: 'rgba(255,255,255,.48)', fontSize: 8, pointerEvents: 'none' }}>{streamMetadata(cam)}</span></div><footer style={{ padding: '5px 9px', display: 'flex', justifyContent: 'space-between', gap: 6, color: 'var(--text2)', fontSize: 10 }}><span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{cam.location || 'Location not registered'}</span><b style={{ color: isLive ? 'var(--green)' : health === 'offline' ? 'var(--red)' : 'var(--text2)', fontSize: 9 }}>{isLive ? 'LIVE' : health.toUpperCase()}</b></footer></article>
})

export default function CameraGrid({ cameras, alertsByCam, analyticsByCam = {}, pipelineStats, onLocate, focusCameraId, focusNonce = 0 }) {
  const [cols, setCols] = useState(() => { const saved = Number(localStorage.getItem('sentinel.camera-grid.columns.v1')); return [2, 3, 4, 5].includes(saved) ? saved : 3 }), [focused, setFocused] = useState(null)
  const handleColChange = n => { setCols(n); localStorage.setItem('sentinel.camera-grid.columns.v1', String(n)) }
  useEffect(() => { if (!focusCameraId) return; const camera = cameras.find(item => item.id === focusCameraId); if (camera) setFocused(camera) }, [focusCameraId, focusNonce, cameras])
  return <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--bg)', overflow: 'hidden' }}><header style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', borderBottom: '1px solid var(--border)', background: 'var(--surface)' }}><CamIcon size={13} color="var(--text2)"/><b style={{ fontSize: 12 }}>{cameras.length} Cameras</b>{pipelineStats && <span style={{ color: 'var(--text2)', fontSize: 10 }}>Frames {Number(pipelineStats.raw_frames || 0).toLocaleString()} · Detections {Number(pipelineStats.detections || 0).toLocaleString()}</span>}<div style={{ marginLeft: 'auto', display: 'flex', gap: 3 }}>{[2, 3, 4, 5].map(n => <button key={n} onClick={() => handleColChange(n)} title={`${n} columns`} aria-label={`${n} camera columns`} style={{ width: 28, height: 28, borderRadius: 5, border: `1px solid ${cols === n ? 'var(--accent)' : 'var(--border)'}`, background: cols === n ? 'var(--accent)22' : 'transparent', color: cols === n ? 'var(--accent)' : 'var(--text2)', cursor: 'pointer' }}><GridIcon n={n}/></button>)}</div></header><main style={{ flex: 1, overflowY: 'auto', padding: 10 }}><div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gap: 8, alignContent: 'start' }}>{cameras.map((cam, index) => <CameraCard key={cam.id} cam={cam} alertCount={alertsByCam[cam.id] || 0} analytics={analyticsByCam[cam.id]} onFocus={setFocused} onLocate={onLocate} animDelay={Math.min(index * 30, 300)}/>)}{!cameras.length && <div style={{ gridColumn: '1 / -1', padding: 48, textAlign: 'center', color: 'var(--text2)' }}>Syncing camera registry…</div>}</div></main>{focused && <FullscreenModal cam={focused} alertCount={alertsByCam[focused.id] || 0} analytics={analyticsByCam[focused.id]} onClose={() => setFocused(null)} onLocate={onLocate}/>}<style>{`@keyframes cardIn{from{opacity:0;transform:translateY(10px) scale(.97)}to{opacity:1;transform:translateY(0) scale(1)}}.camera-card:hover .camera-actions,.camera-card:focus-within .camera-actions{opacity:1!important;transform:translateY(0)!important}`}</style></div>
}
