import { useState, useEffect, useRef, useCallback, memo } from 'react'
import Hls from 'hls.js'

// ─── Constants ───────────────────────────────────────────────────────────────
const PRIO_BORDER = { HIGH: 'var(--high)', MEDIUM: 'var(--medium)', LOW: 'var(--low)' }
const streamMetadata = (cam) => {
  const width = cam.effective_width ?? cam.width
  const height = cam.effective_height ?? cam.height
  const fps = cam.effective_fps ?? cam.fps
  return `${cam.effective_codec || cam.codec || 'Unknown'} · ${width && height ? `${width}×${height}` : 'N/A'} · ${fps == null ? 'N/A' : `${Number(fps).toFixed(1)} fps`}`
}

// ─── CameraIcon SVG (no emoji) ────────────────────────────────────────────────
const CamIcon = ({ size = 14, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M15 10l4.553-2.069A1 1 0 0121 8.82v6.36a1 1 0 01-1.447.893L15 14"/>
    <rect x="1" y="6" width="15" height="12" rx="2" ry="2"/>
  </svg>
)

const CloseIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <line x1="18" y1="6" x2="6" y2="18"/>
    <line x1="6" y1="6" x2="18" y2="18"/>
  </svg>
)

const GridIcon = ({ n }) => (
  <svg width="14" height="14" viewBox="0 0 12 12" fill="currentColor">
    {n === 2 && <><rect x="0" y="0" width="5" height="12" rx="1"/><rect x="7" y="0" width="5" height="12" rx="1"/></>}
    {n === 3 && <><rect x="0" y="0" width="3" height="12" rx="1"/><rect x="4.5" y="0" width="3" height="12" rx="1"/><rect x="9" y="0" width="3" height="12" rx="1"/></>}
    {n === 4 && <><rect x="0" y="0" width="2.5" height="5.5" rx="0.5"/><rect x="3.2" y="0" width="2.5" height="5.5" rx="0.5"/><rect x="6.3" y="0" width="2.5" height="5.5" rx="0.5"/><rect x="9.5" y="0" width="2.5" height="5.5" rx="0.5"/><rect x="0" y="6.5" width="2.5" height="5.5" rx="0.5"/><rect x="3.2" y="6.5" width="2.5" height="5.5" rx="0.5"/><rect x="6.3" y="6.5" width="2.5" height="5.5" rx="0.5"/><rect x="9.5" y="6.5" width="2.5" height="5.5" rx="0.5"/></>}
    {n === 5 && <><rect x="0" y="0" width="2" height="5.5" rx="0.5"/><rect x="2.5" y="0" width="2" height="5.5" rx="0.5"/><rect x="5" y="0" width="2" height="5.5" rx="0.5"/><rect x="7.5" y="0" width="2" height="5.5" rx="0.5"/><rect x="10" y="0" width="2" height="5.5" rx="0.5"/><rect x="0" y="6.5" width="2" height="5.5" rx="0.5"/><rect x="2.5" y="6.5" width="2" height="5.5" rx="0.5"/><rect x="5" y="6.5" width="2" height="5.5" rx="0.5"/><rect x="7.5" y="6.5" width="2" height="5.5" rx="0.5"/><rect x="10" y="6.5" width="2" height="5.5" rx="0.5"/></>}
  </svg>
)

// ─── LivePlayer ───────────────────────────────────────────────────────────────
// Fallback chain: hls_url → stream URL → JPEG snapshot → error
// No iframe, no external page navigation.
function LivePlayer({ cam, muted = true, onLiveStatus }) {
  const videoRef  = useRef(null)
  const hlsRef    = useRef(null)
  const timerRef  = useRef(null)
  const [mode,    setMode]    = useState(cam.hls_url ? 'hls' : 'stream')
  const [snapUrl, setSnapUrl] = useState(null)
  const [live,    setLive]    = useState(false)   // true = video actually playing

  const streamUrl   = `https://live.corp8.cloud/stream/${cam.stream_id}`
  const snapshotUrl = `/api/cameras/${cam.id}/snapshot`

  const advance = useCallback((from) => {
    const chain = { hls: 'stream', stream: 'snapshot', snapshot: 'error' }
    setMode(chain[from] || 'error')
    setLive(false)
  }, [])

  // Notify parent of live status
  useEffect(() => { onLiveStatus?.(live) }, [live, onLiveStatus])

  // Reset when camera changes
  useEffect(() => {
    hlsRef.current?.destroy(); hlsRef.current = null
    clearInterval(timerRef.current)
    setMode(cam.hls_url ? 'hls' : 'stream')
    setSnapUrl(null)
    setLive(false)
  }, [cam.id, cam.hls_url])

  // HLS mode
  useEffect(() => {
    if (mode !== 'hls' || !cam.hls_url) {
      if (mode === 'hls') advance('hls')
      return
    }
    const video = videoRef.current
    if (!video) return

    if (Hls.isSupported()) {
      const hls = new Hls({ enableWorker: true, lowLatencyMode: true, backBufferLength: 6 })
      hls.loadSource(cam.hls_url)
      hls.attachMedia(video)
      hls.on(Hls.Events.ERROR, (_, d) => { if (d.fatal) { hls.destroy(); advance('hls') } })
      hlsRef.current = hls
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = cam.hls_url
    } else {
      advance('hls')
    }
    return () => { hlsRef.current?.destroy(); hlsRef.current = null }
  }, [mode, cam.hls_url, advance])

  // Direct stream mode (no iframe — just a video src)
  useEffect(() => {
    if (mode !== 'stream') return
    const video = videoRef.current
    if (!video) return
    video.src = streamUrl
    const onPlay = () => setLive(true)
    const onErr  = () => advance('stream')
    video.addEventListener('playing', onPlay)
    video.addEventListener('error',   onErr)
    video.play().catch(() => {})
    return () => { video.removeEventListener('playing', onPlay); video.removeEventListener('error', onErr) }
  }, [mode, streamUrl, advance])

  // JPEG snapshot polling
  useEffect(() => {
    if (mode !== 'snapshot') return
    const load = () => setSnapUrl(`${snapshotUrl}?t=${Date.now()}`)
    load()
    timerRef.current = setInterval(load, 2500)
    return () => clearInterval(timerRef.current)
  }, [mode, snapshotUrl])

  const showVideo = mode === 'hls' || mode === 'stream'

  return (
    <div style={{ position:'absolute', inset:0, background:'#000' }}>
      {/* Shared video element for HLS and stream modes */}
      <video
        ref={videoRef}
        autoPlay muted={muted} playsInline
        onPlaying={() => setLive(true)}
        onWaiting={() => setLive(false)}
        onStalled={() => {}}
        style={{
          position:'absolute', inset:0, width:'100%', height:'100%',
          objectFit:'cover', display: showVideo ? 'block' : 'none',
        }}
      />

      {/* Snapshot */}
      {mode === 'snapshot' && snapUrl && (
        <img src={snapUrl} alt=""
          style={{ position:'absolute', inset:0, width:'100%', height:'100%', objectFit:'cover' }}
          onLoad={() => setLive(true)}
          onError={() => { setLive(false); advance('snapshot') }}
        />
      )}

      {/* Error / connecting states */}
      {(mode === 'error' || (mode === 'snapshot' && !snapUrl)) && (
        <div style={{
          position:'absolute', inset:0, display:'flex', flexDirection:'column',
          alignItems:'center', justifyContent:'center', gap:8, color:'var(--text2)',
        }}>
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="1.5" opacity=".4">
            <path d="M3 3l18 18M15 10l4.553-2.069A1 1 0 0121 8.82v6.36a1 1 0 01-1.447.893L15 14M5 8H3a1 1 0 00-1 1v9a1 1 0 001 1h14"/>
          </svg>
          <span style={{ fontSize:11 }}>Feed unavailable</span>
        </div>
      )}

      {(mode === 'hls' || mode === 'stream') && !live && (
        <div style={{
          position:'absolute', inset:0, display:'flex', alignItems:'center',
          justifyContent:'center', background:'rgba(0,0,0,.5)', pointerEvents:'none',
        }}>
          <div style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:6 }}>
            <div style={{ width:20, height:20, border:'2px solid rgba(255,255,255,.2)',
                          borderTopColor:'rgba(255,255,255,.7)', borderRadius:'50%',
                          animation:'spin .8s linear infinite' }}/>
            <span style={{ fontSize:10, color:'rgba(255,255,255,.5)' }}>Connecting</span>
          </div>
        </div>
      )}

      {/* LIVE badge — only when genuinely playing */}
      {live && (
        <div style={{
          position:'absolute', bottom:6, right:8,
          display:'flex', alignItems:'center', gap:3, pointerEvents:'none',
        }}>
          <span style={{
            width:5, height:5, borderRadius:'50%',
            background:'#f85149', animation:'blink 1.2s ease-in-out infinite',
          }}/>
          <span style={{ fontSize:9, color:'rgba(255,255,255,.7)', letterSpacing:.5 }}>LIVE</span>
        </div>
      )}
    </div>
  )
}

// ─── FullscreenModal ──────────────────────────────────────────────────────────
function FullscreenModal({ cam, alertCount, onClose }) {
  const padded = String(cam.stream_id || '?').padStart(2, '0')

  // Escape key to close
  useEffect(() => {
    const h = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  // Prevent body scroll while open
  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = '' }
  }, [])

  return (
    <div
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
      style={{
        position:'fixed', inset:0, zIndex:2000,
        background:'rgba(0,0,0,.88)',
        display:'flex', alignItems:'center', justifyContent:'center',
        animation:'overlayFade .15s ease',
      }}
    >
      <div style={{
        width:'92vw', height:'88vh', maxWidth:1440,
        background:'var(--surface)', borderRadius:10,
        border:'1px solid var(--border)',
        display:'flex', flexDirection:'column', overflow:'hidden',
        boxShadow:'0 32px 96px rgba(0,0,0,.8)',
        animation:'modalZoom .22s cubic-bezier(.34,1.4,.64,1)',
      }}>
        {/* Header */}
        <div style={{
          display:'flex', alignItems:'center', gap:12, padding:'10px 16px',
          borderBottom:'1px solid var(--border)', flexShrink:0,
          background:'var(--surface2)',
        }}>
          <CamIcon size={16} color="var(--accent)"/>
          <span style={{ fontWeight:700, fontSize:14, letterSpacing:.3 }}>
            CAM-{padded}
          </span>
          <span style={{ color:'var(--text2)', fontSize:13 }}>{cam.name}</span>
          <div style={{ marginLeft:'auto', display:'flex', alignItems:'center', gap:12 }}>
            <span style={{ fontSize:11, color:'var(--text2)' }}>
              {streamMetadata(cam)}
            </span>
            {alertCount > 0 && (
              <span style={{
                background:'var(--high)', color:'#fff',
                borderRadius:4, fontSize:11, fontWeight:700, padding:'2px 8px',
              }}>
                {alertCount} alerts
              </span>
            )}
            <button onClick={onClose} style={{
              background:'rgba(255,255,255,.06)', border:'1px solid var(--border)',
              borderRadius:6, color:'var(--text2)', cursor:'pointer',
              display:'flex', alignItems:'center', justifyContent:'center',
              width:30, height:30, padding:0, transition:'background .15s',
            }}>
              <CloseIcon/>
            </button>
          </div>
        </div>

        {/* Feed */}
        <div style={{ flex:1, position:'relative', overflow:'hidden' }}>
          <LivePlayer cam={cam} muted={false}/>
        </div>

        {/* Footer */}
        <div style={{
          padding:'8px 16px', borderTop:'1px solid var(--border)',
          display:'flex', alignItems:'center', justifyContent:'space-between',
          background:'var(--surface2)', flexShrink:0,
        }}>
          <span style={{ fontSize:12, color:'var(--text2)' }}>{cam.location || '—'}</span>
          <span style={{ fontSize:11, color:'var(--text2)' }}>
            RTSP stream {cam.stream_id} &middot; Press Esc to close
          </span>
        </div>
      </div>

      <style>{`
        @keyframes overlayFade { from{opacity:0} to{opacity:1} }
        @keyframes modalZoom   { from{transform:scale(.08);opacity:0} to{transform:scale(1);opacity:1} }
      `}</style>
    </div>
  )
}

// ─── CameraCard ───────────────────────────────────────────────────────────────
const CameraCard = memo(function CameraCard({ cam, alertCount, onFocus, animDelay }) {
  const [isLive, setIsLive] = useState(false)
  const padded = String(cam.stream_id || '?').padStart(2, '0')
  const hasPrioAlerts = alertCount > 0

  return (
    <div
      onClick={() => onFocus(cam)}
      style={{
        background:'var(--surface2)', borderRadius:8, overflow:'hidden',
        border:`1px solid ${hasPrioAlerts ? 'var(--high)' : 'var(--border)'}`,
        boxShadow: hasPrioAlerts ? '0 0 14px rgba(248,81,73,.25)' : 'none',
        display:'flex', flexDirection:'column', cursor:'pointer',
        transition:'border .25s, box-shadow .25s, transform .15s',
        animation:`cardIn .22s ease ${animDelay}ms both`,
      }}
      onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-2px)'}
      onMouseLeave={e => e.currentTarget.style.transform = 'translateY(0)'}
    >
      {/* 16:9 video area */}
      <div style={{ position:'relative', paddingTop:'56.25%', overflow:'hidden', background:'#000' }}>
        <LivePlayer cam={cam} muted onLiveStatus={setIsLive}/>

        {/* Top overlay: cam ID + name (pointer-events:none so clicks fall through) */}
        <div style={{
          position:'absolute', top:0, left:0, right:0, pointerEvents:'none',
          background:'linear-gradient(rgba(0,0,0,.72) 0%, transparent 100%)',
          padding:'6px 8px', display:'flex', alignItems:'center', gap:6,
        }}>
          <span style={{
            fontSize:10, fontWeight:700, color:'rgba(255,255,255,.55)',
            letterSpacing:.5, minWidth:44,
          }}>
            CAM-{padded}
          </span>
          <span style={{
            fontSize:10, color:'rgba(255,255,255,.85)', fontWeight:600,
            overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', flex:1,
          }}>
            {cam.name}
          </span>
          {/* Status dot — from DB only if not live, otherwise always green */}
          <span style={{
            width:6, height:6, borderRadius:'50%', flexShrink:0,
            background: isLive ? 'var(--green)' : (cam.status === 'offline' ? 'var(--red)' : 'var(--yellow)'),
            boxShadow: isLive ? '0 0 5px var(--green)' : 'none',
          }}/>
        </div>

        {/* Alert count badge */}
        {hasPrioAlerts && (
          <div style={{
            position:'absolute', top:6, right:10, pointerEvents:'none',
            background:'var(--high)', color:'#fff',
            borderRadius:4, fontSize:9, fontWeight:700, padding:'1px 5px',
            letterSpacing:.3,
          }}>
            {alertCount}
          </div>
        )}

        {/* Bottom-left: codec + resolution */}
        <div style={{
          position:'absolute', bottom:5, left:7, pointerEvents:'none',
          fontSize:8, color:'rgba(255,255,255,.4)', letterSpacing:.3,
        }}>
          {streamMetadata(cam)}
        </div>
      </div>

      {/* Card footer */}
      <div style={{
        padding:'5px 9px', display:'flex',
        justifyContent:'space-between', alignItems:'center', flexShrink:0,
      }}>
        <span style={{
          fontSize:10, color:'var(--text2)', overflow:'hidden',
          textOverflow:'ellipsis', whiteSpace:'nowrap', flex:1,
        }}>
          {cam.location || '\u00a0'}
        </span>
        <span style={{
          fontSize:9, fontWeight:600, letterSpacing:.4, marginLeft:6, flexShrink:0,
          color: isLive ? 'var(--green)' : (cam.status === 'offline' ? 'var(--red)' : 'var(--text2)'),
        }}>
          {isLive ? 'LIVE' : cam.status?.toUpperCase()}
        </span>
      </div>
    </div>
  )
})

// ─── CameraGrid (default export) ──────────────────────────────────────────────
export default function CameraGrid({ cameras, alertsByCam, pipelineStats }) {
  const [cols,    setCols]    = useState(() => {
    const saved = Number(localStorage.getItem('sentinel.camera-grid.columns.v1'))
    return [2, 3, 4, 5].includes(saved) ? saved : 3
  })
  const [focused, setFocused] = useState(null)   // cam object or null

  const handleColChange = (n) => {
    setCols(n)
    localStorage.setItem('sentinel.camera-grid.columns.v1', String(n))
  }

  return (
    <div style={{
      display:'flex', flexDirection:'column', height:'100%',
      background:'var(--bg)', overflow:'hidden',
    }}>
      {/* Toolbar */}
      <div style={{
        display:'flex', alignItems:'center', gap:10, padding:'8px 12px',
        borderBottom:'1px solid var(--border)', flexShrink:0,
        background:'var(--surface)',
      }}>
        <CamIcon size={13} color="var(--text2)"/>
        <span style={{ fontSize:12, fontWeight:600, color:'var(--text)' }}>
          {cameras.length} Cameras
        </span>

        {/* Pipeline health indicators */}
        {pipelineStats && (
          <div style={{ display:'flex', gap:10, marginLeft:8 }}>
            {[
              ['Frames',     pipelineStats.raw_frames,  'var(--green)'],
              ['Detections', pipelineStats.detections,  'var(--accent)'],
              ['Alerts',     pipelineStats.alerts,      'var(--medium)'],
            ].map(([label, val, color]) => (
              <div key={label} style={{ display:'flex', alignItems:'center', gap:4 }}>
                <span style={{ fontSize:9, color:'var(--text2)' }}>{label}</span>
                <span style={{ fontSize:10, fontWeight:700, color, fontVariantNumeric:'tabular-nums' }}>
                  {(val || 0).toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Column selector */}
        <div style={{ marginLeft:'auto', display:'flex', gap:3 }}>
          {[2, 3, 4, 5].map(n => (
            <button
              key={n} onClick={() => handleColChange(n)}
              title={`${n} columns`}
              style={{
                width:28, height:28, borderRadius:5,
                border:`1px solid ${cols === n ? 'var(--accent)' : 'var(--border)'}`,
                background: cols === n ? 'var(--accent)22' : 'transparent',
                color: cols === n ? 'var(--accent)' : 'var(--text2)',
                cursor:'pointer', display:'flex', alignItems:'center', justifyContent:'center',
                transition:'border .15s, background .15s, color .15s',
              }}
            >
              <GridIcon n={n}/>
            </button>
          ))}
        </div>
      </div>

      {/* Grid */}
      <div style={{ flex:1, overflowY:'auto', padding:10 }}>
        <div
          style={{
            display:'grid',
            gridTemplateColumns:`repeat(${cols}, minmax(0, 1fr))`,
            gap:8,
            alignContent:'start',
          }}
        >
          {cameras.map((cam, i) => (
            <CameraCard
              key={cam.id}
              cam={cam}
              alertCount={alertsByCam[cam.id] || 0}
              onFocus={setFocused}
              animDelay={Math.min(i * 30, 300)}
            />
          ))}

          {cameras.length === 0 && (
            <div style={{
              gridColumn:'1 / -1', padding:48, textAlign:'center',
              color:'var(--text2)', fontSize:13,
            }}>
              Syncing camera catalogue from live.corp8.cloud…
            </div>
          )}
        </div>
      </div>

      {/* Fullscreen modal */}
      {focused && (
        <FullscreenModal
          cam={focused}
          alertCount={alertsByCam[focused.id] || 0}
          onClose={() => setFocused(null)}
        />
      )}

      <style>{`
        @keyframes blink   { 0%,100%{opacity:1} 50%{opacity:.15} }
        @keyframes spin    { to{transform:rotate(360deg)} }
        @keyframes cardIn  { from{opacity:0;transform:translateY(10px) scale(.97)} to{opacity:1;transform:translateY(0) scale(1)} }
      `}</style>
    </div>
  )
}
