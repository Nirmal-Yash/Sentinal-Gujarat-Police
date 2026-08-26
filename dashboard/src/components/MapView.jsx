import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const GUJARAT_BOUNDS = L.latLngBounds([20.08, 68.08], [24.8, 74.55])
const VIEW_KEY = 'sentinel.map.viewport.v1'
const SELECTED_KEY = 'sentinel.map.selected-camera.v1'
const PRIO_COLOR = { HIGH: '#f85149', MEDIUM: '#d29922', LOW: '#3fb950' }
const hasCoordinates = cam => cam?.lat !== null && cam?.lat !== undefined && cam?.lng !== null && cam?.lng !== undefined && Number.isFinite(Number(cam.lat)) && Number.isFinite(Number(cam.lng))
const needsCoordinateReview = cam => cam?.coord_source === 'default' || Number(cam?.coord_confidence) < 0.4

function statusColor(cam) {
  const status = cam.health_status || cam.status
  if (status === 'healthy' || status === 'active') return '#3fb950'
  if (status === 'degraded' || status === 'reconnecting') return '#d29922'
  if (status === 'offline' || status === 'critical') return '#f85149'
  return '#8b949e'
}

function displayMetadata(cam) {
  const width = cam.effective_width ?? cam.width
  const height = cam.effective_height ?? cam.height
  const fps = cam.effective_fps ?? cam.fps
  return `${cam.effective_codec || cam.codec || 'Unknown'} · ${width && height ? `${width}×${height}` : 'N/A'} · ${fps == null ? 'N/A' : `${Number(fps).toFixed(1)} fps`}`
}

function accurateMetadata(cam) {
  const width = cam.effective_width ?? cam.width
  const height = cam.effective_height ?? cam.height
  const fps = cam.effective_fps ?? cam.fps
  const values = []
  if (cam.effective_codec || cam.codec) values.push(cam.effective_codec || cam.codec)
  if (Number(width) > 0 && Number(height) > 0) values.push(`${width} x ${height}`)
  if (Number(fps) > 0) values.push(`${Number(fps).toFixed(1)} FPS`)
  return values.join(' · ') || 'Stream metadata unavailable'
}

function camIcon(cam, selected = false) {
  const color = statusColor(cam)
  const warning = needsCoordinateReview(cam) ? '<span style="position:absolute;right:-5px;top:-5px;width:12px;height:12px;border-radius:50%;background:#d29922;border:1px solid #fff;color:#111;font:700 10px system-ui;text-align:center">!</span>' : ''
  return L.divIcon({ className: '', iconSize: [30, 38], iconAnchor: [15, 38], popupAnchor: [0, -34], html: `<div style="position:relative;width:30px;height:30px;border-radius:50% 50% 50% 0;background:${color};border:3px solid ${selected ? '#58a6ff' : '#fff'};transform:rotate(-45deg);box-shadow:0 2px 8px rgba(0,0,0,.6)"><svg style="transform:rotate(45deg);position:absolute;left:7px;top:7px" width="11" height="11" viewBox="0 0 24 24" fill="#fff"><path d="M15 10l4.553-2.069A1 1 0 0121 8.82v6.36a1 1 0 01-1.447.893L15 14M3 8a2 2 0 012-2h10a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z"/></svg>${warning}</div>` })
}

function clusterIcon(count) {
  return L.divIcon({ className: '', iconSize: [34, 34], iconAnchor: [17, 17], html: `<div style="width:30px;height:30px;border-radius:50%;display:grid;place-items:center;background:#1f6feb;color:white;border:2px solid white;box-shadow:0 1px 6px #000;font:700 11px system-ui">${count}</div>` })
}

function popupForRegistryCamera(cam) {
  const coordinateNotice = needsCoordinateReview(cam) ? '<br/><span style="font-size:11px;color:#9a6700;font-weight:700">Coordinate review required</span>' : ''
  return `<div style="font-family:system-ui;font-size:12px;min-width:190px"><b>CAM-${String(cam.stream_id || '?').padStart(2, '0')} · ${cam.name}</b><br/><span style="color:#555">${cam.location || 'Location not registered'}</span><br/><span style="color:#555">${cam.department || 'Unassigned'} · ${cam.camera_type || 'fixed'}</span><br/><span style="font-size:11px;color:#777">${accurateMetadata(cam)}</span><br/><span style="font-size:11px;color:${statusColor(cam)};font-weight:700">${(cam.health_status || cam.status || 'unknown').toUpperCase()}</span>${coordinateNotice}</div>`
}

export default function MapView({ cameras, alerts, compact = false, focusCameraId, focusNonce = 0, route = [], routeFocusNonce = 0 }) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const cameraLayerRef = useRef(null)
  const coverageLayerRef = useRef(null)
  const alertLayerRef = useRef(null)
  const routeLayerRef = useRef(null)
  const markersRef = useRef({})
  const camerasRef = useRef([])
  const selectedRef = useRef(localStorage.getItem(SELECTED_KEY) || null)
  const [notice, setNotice] = useState('')

  const refreshVisibleLayer = () => {
    const map = mapRef.current; const layer = cameraLayerRef.current
    if (!map || !layer) return
    layer.clearLayers()
    const cameras = camerasRef.current.filter(hasCoordinates)
    if (map.getZoom() > 9) { cameras.forEach(cam => layer.addLayer(markersRef.current[cam.id].marker)); return }
    const cells = new Map(); const divisor = Math.max(0.08, 1.2 / Math.max(map.getZoom(), 1))
    cameras.forEach(cam => { const key = `${Math.floor(cam.lat / divisor)}:${Math.floor(cam.lng / divisor)}`; const cell = cells.get(key) || []; cell.push(cam); cells.set(key, cell) })
    cells.forEach(items => {
      if (items.length === 1) return layer.addLayer(markersRef.current[items[0].id].marker)
      const bounds = L.latLngBounds(items.map(c => [c.lat, c.lng]))
      const marker = L.marker(bounds.getCenter(), { icon: clusterIcon(items.length), keyboard: true, title: `${items.length} cameras` })
      marker.on('click', () => map.fitBounds(bounds.pad(0.5), { maxZoom: 12 })); layer.addLayer(marker)
    })
  }

  const selectCamera = (cameraId, { focus = false } = {}) => {
    const map = mapRef.current
    const selected = markersRef.current[cameraId]
    if (!map || !selected) return false
    selectedRef.current = cameraId
    localStorage.setItem(SELECTED_KEY, cameraId)
    Object.values(markersRef.current).forEach(item =>
      item.marker.setIcon(camIcon(item.camera, item.camera.id === cameraId)))
    if (focus) {
      map.setView(selected.marker.getLatLng(), Math.max(map.getZoom(), 15), { animate: true })
      selected.marker.openPopup()
    }
    return true
  }

  useEffect(() => {
    if (mapRef.current || !containerRef.current) return
    let saved; try { saved = JSON.parse(localStorage.getItem(VIEW_KEY) || 'null') } catch { saved = null }
    const map = L.map(containerRef.current, { center: saved?.center || GUJARAT_BOUNDS.getCenter(), zoom: saved?.zoom || 7, zoomControl: true })
    const streets = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OpenStreetMap contributors', maxZoom: 19 }).addTo(map)
    const satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { attribution: 'Tiles © Esri', maxZoom: 19 })
    const camerasLayer = L.layerGroup().addTo(map), coverageLayer = L.layerGroup(), alertLayer = L.layerGroup().addTo(map), routeLayer = L.layerGroup().addTo(map)
    cameraLayerRef.current = camerasLayer; coverageLayerRef.current = coverageLayer; alertLayerRef.current = alertLayer; routeLayerRef.current = routeLayer; mapRef.current = map
    L.control.layers({ Streets: streets, Satellite: satellite }, { 'Camera clusters': camerasLayer, 'Coverage / density': coverageLayer, 'Recent alerts': alertLayer, 'Vehicle route': routeLayer }, { collapsed: compact }).addTo(map)
    L.control.scale({ imperial: false }).addTo(map)
    const reset = L.Control.extend({ onAdd() { const b = L.DomUtil.create('button', 'leaflet-bar'); b.type = 'button'; b.title = 'Reset to Gujarat'; b.textContent = 'GJ'; b.style.cssText = 'width:30px;height:30px;background:#fff;border:0;font-weight:700;cursor:pointer'; L.DomEvent.on(b, 'click', e => { L.DomEvent.stop(e); map.fitBounds(GUJARAT_BOUNDS) }); return b } })
    const fullscreen = L.Control.extend({ onAdd() { const b = L.DomUtil.create('button', 'leaflet-bar'); b.type = 'button'; b.title = 'Fullscreen map'; b.textContent = '⛶'; b.style.cssText = 'width:30px;height:30px;background:#fff;border:0;font-size:18px;cursor:pointer'; L.DomEvent.on(b, 'click', e => { L.DomEvent.stop(e); containerRef.current?.requestFullscreen?.() }); return b } })
    map.addControl(new reset({ position: 'topleft' })); map.addControl(new fullscreen({ position: 'topleft' }))
    const legend = L.control({ position: 'bottomright' }); legend.onAdd = () => { const d = L.DomUtil.create('div'); d.style.cssText = 'background:rgba(255,255,255,.94);padding:6px 8px;border-radius:4px;font:11px system-ui;color:#222'; d.innerHTML = '<b>Camera health</b><br><span style="color:#3fb950">●</span> Healthy &nbsp; <span style="color:#d29922">●</span> Degraded<br><span style="color:#f85149">●</span> Offline &nbsp; <span style="color:#8b949e">●</span> Unknown'; return d }; legend.addTo(map)
    map.on('moveend', () => { const c = map.getCenter(); localStorage.setItem(VIEW_KEY, JSON.stringify({ center: [c.lat, c.lng], zoom: map.getZoom() })) }); map.on('zoomend', refreshVisibleLayer)
    requestAnimationFrame(() => map.invalidateSize())
    return () => { map.remove(); mapRef.current = null }
  }, [])

  useEffect(() => {
    if (!mapRef.current) return
    const incoming = new Set(cameras.map(c => c.id))
    Object.entries(markersRef.current).forEach(([id, item]) => { if (!incoming.has(id)) { item.marker.remove(); delete markersRef.current[id] } })
    cameras.forEach(cam => {
      if (!hasCoordinates(cam)) return
      const current = markersRef.current[cam.id]
      if (current) { current.marker.setLatLng([cam.lat, cam.lng]).setIcon(camIcon(cam, selectedRef.current === cam.id)).bindPopup(popupForRegistryCamera(cam)); current.camera = cam; return }
      const marker = L.marker([cam.lat, cam.lng], { icon: camIcon(cam, selectedRef.current === cam.id), title: cam.name }).bindPopup(popupForRegistryCamera(cam))
      marker.on('click', () => selectCamera(cam.id))
      markersRef.current[cam.id] = { marker, camera: cam }
    })
    camerasRef.current = cameras; coverageLayerRef.current?.clearLayers()
    cameras.filter(hasCoordinates).forEach(cam => coverageLayerRef.current?.addLayer(L.circle([cam.lat, cam.lng], { radius: 450, color: statusColor(cam), weight: 1, fillOpacity: .06, interactive: false })))
    refreshVisibleLayer()
  }, [cameras])

  useEffect(() => {
    if (!focusCameraId) return
    const camera = cameras.find(item => item.id === focusCameraId)
    if (!camera || !hasCoordinates(camera)) {
      setNotice(`${camera?.name || 'Selected camera'} has no verified registry coordinates. Add latitude and longitude through camera onboarding to place it on the map.`)
      return
    }
    setNotice('')
    selectCamera(focusCameraId, { focus: true })
  }, [focusCameraId, focusNonce, cameras])
  useEffect(() => { const layer = alertLayerRef.current; if (!layer) return; layer.clearLayers(); alerts.slice(0, 30).forEach(alert => { const cam = camerasRef.current.find(c => c.id === alert.cam_id); if (hasCoordinates(cam)) layer.addLayer(L.circle([cam.lat, cam.lng], { radius: 250, color: PRIO_COLOR[alert.priority] || '#8b949e', weight: 2, fillOpacity: .14, interactive: false })) }) }, [alerts])
  useEffect(() => {
    const layer = routeLayerRef.current
    const map = mapRef.current
    if (!layer) return
    layer.clearLayers()
    const points = route.filter(hasCoordinates).map(s => [s.lat, s.lng])
    if (!points.length) return
    layer.addLayer(L.polyline(points, { color: '#58a6ff', weight: 4, opacity: .8 }))
    if (routeFocusNonce && map) {
      if (points.length === 1) map.setView(points[0], Math.max(map.getZoom(), 15), { animate: true })
      else map.fitBounds(L.latLngBounds(points).pad(0.2), { maxZoom: 15, animate: true })
    }
  }, [route, routeFocusNonce])
  useEffect(() => { const map = mapRef.current; if (!map) return; const observer = new ResizeObserver(() => map.invalidateSize({ pan: false })); observer.observe(containerRef.current); requestAnimationFrame(() => map.invalidateSize({ pan: false })); return () => observer.disconnect() }, [compact])
  const mappedCount = cameras.filter(hasCoordinates).length
  const reviewCount = cameras.filter(needsCoordinateReview).length
  const registryNotice = mappedCount ? '' : 'No camera locations are available in the canonical registry yet. Import verified latitude and longitude; the map will then cluster and display them automatically.'
  return <div style={{ position: 'relative', height: '100%', width: '100%' }}>
    <div ref={containerRef} style={{ height: '100%', width: '100%', background: '#1a1f2e' }} />
    {(notice || registryNotice) && <div style={{ position: 'absolute', top: 12, left: 52, maxWidth: 460, padding: '8px 10px', borderRadius: 6, background: 'rgba(18,24,34,.94)', border: '1px solid var(--border)', color: 'var(--text)', fontSize: 11, pointerEvents: 'none' }}>{notice || registryNotice}</div>}
    <div style={{ position: 'absolute', right: 12, top: 12, padding: '5px 8px', borderRadius: 5, background: 'rgba(18,24,34,.9)', color: 'var(--text2)', fontSize: 10, pointerEvents: 'none' }}>{mappedCount}/{cameras.length} mapped{reviewCount ? ` · ${reviewCount} need review` : ''}</div>
  </div>
}
