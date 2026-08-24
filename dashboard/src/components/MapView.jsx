import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// Fix default marker icons broken by bundlers
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl:       'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl:     'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

const PRIO_COLOR = { HIGH: '#f85149', MEDIUM: '#d29922', LOW: '#3fb950' }

function camIcon(cam) {
  const bg = cam.status === 'active' ? '#3fb950' : '#8b949e'
  return L.divIcon({
    className: '',
    html: `<div style="
      width:22px;height:22px;border-radius:50%;
      background:${bg};border:2px solid #fff;
      box-shadow:0 1px 5px rgba(0,0,0,.6);
      display:flex;align-items:center;justify-content:center;
    ">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="#fff">
        <path d="M15 10l4.553-2.069A1 1 0 0121 8.82v6.36a1 1 0 01-1.447.893L15 14M3 8a2 2 0 012-2h10a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z"/>
      </svg>
    </div>`,
    iconSize:   [22, 22],
    iconAnchor: [11, 11],
    popupAnchor:[0, -12],
  })
}

export default function MapView({ cameras, alerts }) {
  const containerRef = useRef(null)
  const mapRef       = useRef(null)
  const markersRef   = useRef({})

  // ── Init map once container has height ───────────────────────────────────
  useEffect(() => {
    if (mapRef.current || !containerRef.current) return

    const map = L.map(containerRef.current, {
      center:      [22.3039, 70.8022],
      zoom:        8,
      zoomControl: true,
    })

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom:     19,
    }).addTo(map)

    mapRef.current = map

    // invalidateSize after render frame to handle flex layout
    requestAnimationFrame(() => map.invalidateSize())

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  // ── Sync camera markers ───────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    cameras.forEach(cam => {
      const existing = markersRef.current[cam.id]
      if (existing) {
        // Update icon if status changed
        existing.setIcon(camIcon(cam))
        return
      }
      const marker = L.marker([cam.lat, cam.lng], { icon: camIcon(cam) })
        .addTo(map)
        .bindPopup(`
          <div style="font-family:system-ui;font-size:13px;min-width:160px">
            <div style="font-weight:700;margin-bottom:4px">
              CAM-${String(cam.stream_id || '?').padStart(2, '0')} &middot; ${cam.name}
            </div>
            <div style="color:#555;margin-bottom:2px">${cam.location || ''}</div>
            <div style="font-size:11px;color:#777">${cam.codec} &middot; ${cam.width}&times;${cam.height}</div>
            <div style="margin-top:6px;font-size:11px;
              color:${cam.status === 'active' ? '#1a7f37' : '#cf222e'}">
              ${cam.status.toUpperCase()}
            </div>
          </div>
        `)
      markersRef.current[cam.id] = marker
    })

    // Fit bounds on first camera load
    if (cameras.length > 0 && Object.keys(markersRef.current).length === cameras.length) {
      try {
        const group = L.featureGroup(Object.values(markersRef.current))
        map.fitBounds(group.getBounds().pad(0.15))
      } catch {}
    }
  }, [cameras])

  // ── Alert pulse rings ─────────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!map || alerts.length === 0) return

    const recent = alerts.slice(0, 15)
    recent.forEach(alert => {
      const cam   = cameras.find(c => c.id === alert.cam_id)
      if (!cam) return
      const color = PRIO_COLOR[alert.priority] || '#8b949e'

      const ring = L.circle([cam.lat, cam.lng], {
        color, weight: 2, fillColor: color, fillOpacity: 0.18, radius: 200,
      }).addTo(map).bindPopup(`
        <div style="font-family:system-ui;font-size:12px">
          <b>${(alert.alert_type || '').replace(/_/g, ' ')}</b><br/>
          Priority: <span style="color:${color};font-weight:700">${alert.priority}</span><br/>
          Confidence: ${((alert.confidence || 0) * 100).toFixed(0)}%
        </div>
      `)

      setTimeout(() => { try { map.removeLayer(ring) } catch {} }, 9000)
    })
  }, [alerts.length]) // eslint-disable-line

  return (
    <div style={{ position: 'relative', height: '100%', width: '100%' }}>
      <div
        ref={containerRef}
        style={{ height: '100%', width: '100%', background: '#1a1f2e' }}
      />
      {cameras.length === 0 && (
        <div style={{
          position: 'absolute', inset: 0, pointerEvents: 'none',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'rgba(13,17,23,.6)', color: 'var(--text2)', fontSize: 13,
        }}>
          Loading cameras…
        </div>
      )}
    </div>
  )
}
