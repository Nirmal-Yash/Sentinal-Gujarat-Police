import { useState, useEffect, useCallback } from 'react'
import { api, WS_URL } from './api/client'
import { useWebSocket } from './hooks/useWebSocket'
import Navbar from './components/Navbar'
import CameraGrid from './components/CameraGrid'
import AlertPanel from './components/AlertPanel'
import MapView from './components/MapView'
import SearchModal from './components/SearchModal'
import WatchlistModal from './components/WatchlistModal'
import OnboardCameraModal from './components/OnboardCameraModal'
import LoginModal from './components/LoginModal'
import VendorModal from './components/VendorModal'
import TestDiagnosticsModal from './components/TestDiagnosticsModal'

const MAX_LIVE_ALERTS = 300
const VALID_ROUTES = new Set(['/dashboard','/feeds','/map','/alerts','/investigations','/test'])
const normalizePath = path => VALID_ROUTES.has(path) ? path : '/dashboard'

function useSpaRoute() {
  const [path, setPath] = useState(() => normalizePath(window.location.pathname))
  useEffect(() => {
    const handlePopState = () => setPath(normalizePath(window.location.pathname))
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])
  const navigate = useCallback(target => {
    const next = normalizePath(target)
    if (window.location.pathname !== next) window.history.pushState({}, '', next)
    setPath(next)
  }, [])
  return [path, navigate]
}

export default function App() {
  const [path, navigate] = useSpaRoute()
  const [cameras, setCameras] = useState([])
  const [productionCameras, setProductionCameras] = useState([])
  const [alerts, setAlerts] = useState([])
  const [counts, setCounts] = useState(null)
  const [pipelineStats, setPipelineStats] = useState(null)
  const [analytics, setAnalytics] = useState([])
  const [mapFocus, setMapFocus] = useState({ id: null, nonce: 0 })
  const [cameraFocus, setCameraFocus] = useState({ id: null, nonce: 0 })
  const [vehicleRoute, setVehicleRoute] = useState({ sightings: [], nonce: 0 })
  const [alertsCollapsed, setAlertsCollapsed] = useState(() => localStorage.getItem('sentinel.alerts.collapsed.v1') === 'true')
  const [showSearch, setShowSearch] = useState(false)
  const [searchInit, setSearchInit] = useState(null)
  const [showWatchlist, setShowWatchlist] = useState(false)
  const [showOnboard, setShowOnboard] = useState(false)
  const [showVendors, setShowVendors] = useState(false)
  const [authRequired, setAuthRequired] = useState(null)
  const [testEnabled, setTestEnabled] = useState(false)
  const [principal, setPrincipal] = useState(null)
  const [authReady, setAuthReady] = useState(false)
  const [authConfigError, setAuthConfigError] = useState('')
  const [showTestDiagnostics, setShowTestDiagnostics] = useState(false)
  const [testMode, setTestMode] = useState(false)
  const [testSession, setTestSession] = useState(null)

  useEffect(() => {
    let active = true
    api.getAuthConfig().then(async config => {
      if (!active) return
      const required = Boolean(config.auth_required)
      setAuthRequired(required)
      setTestEnabled(Boolean(config.test_enabled))
      const token = localStorage.getItem('sentinel.jwt')
      if (!token) {
        setPrincipal(required ? null : { id: null, username: 'local-development', role: 'SUPERADMIN' })
        setAuthReady(true)
        return
      }
      try {
        const me = await api.getMe()
        if (!active) return
        setPrincipal(me)
        setAuthReady(true)
        setAuthConfigError('')
      } catch (error) {
        if (!active) return
        localStorage.removeItem('sentinel.jwt')
        setPrincipal(null)
        setAuthReady(true)
        if (required && error?.message?.startsWith('401')) setAuthConfigError('Your session has expired. Please sign in again.')
      }
    }).catch(error => {
      if (!active) return
      setAuthRequired(true)
      setTestEnabled(false)
      setPrincipal(null)
      setAuthConfigError(error?.message || 'Authentication service unavailable')
      setAuthReady(true)
    })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (path === '/investigations' && authReady && !showSearch) setShowSearch(true)
    if (path === '/test' && authReady && testEnabled && !testMode && !showTestDiagnostics) setShowTestDiagnostics(true)
    if (path !== '/investigations' && showSearch && !searchInit) setShowSearch(false)
  }, [path, authReady, testEnabled, testMode, showTestDiagnostics, showSearch, searchInit])

  const alertsByCam = (alerts || []).reduce((acc, a) => { if (a.cam_id && !a.acknowledged) acc[a.cam_id] = (acc[a.cam_id] || 0) + 1; return acc }, {})
  const analyticsByCam = (analytics || []).reduce((acc, item) => { if (item.cam_id) acc[item.cam_id] = item; return acc }, {})

  useEffect(() => {
    if (!authReady || (authRequired && !principal) || testMode) return
    api.getCameras().then(rows => { setCameras(rows); setProductionCameras(rows) }).catch(console.warn)
    api.getAlertCounts().then(setCounts).catch(console.warn)
    api.getRecentAnalytics().then(setAnalytics).catch(console.warn)
    api.getAlerts({ limit:80 }).then(rows => setAlerts(rows.map(r => ({ ...r, _new:false })))).catch(console.warn)
  }, [authReady, authRequired, principal, testMode])

  useEffect(() => {
    if (!testMode || !testSession) return
    const refresh = async () => {
      try {
        const [testCameras, result, status] = await Promise.all([api.getTestCameras(testSession.id), api.getTestResults(testSession.id), api.getTestStatus(testSession.id)])
        setCameras(testCameras)
        setAlerts((result.alerts || []).map(alert => ({ ...alert, id:alert.id, alert_id:alert.id, cam_id:null, _new:false })))
        setCounts({ total:status.alerts || 0, unacknowledged:status.alerts || 0, high:0, medium:0, low:status.alerts || 0 })
        setPipelineStats({ raw_frames:status.frames_processed || 0, detections:status.detections || 0 })
        setAnalytics((result.detections || []).filter(item => item.plate_text).reduce((latest, item) => {
          const camera = testCameras.find(value => value.stream_id === item.stream_id), cam_id = camera?.id
          if (cam_id && !latest.some(value => value.cam_id === cam_id)) latest.push({ cam_id, plate_text:item.plate_text, confidence:item.confidence, bbox:item.bbox, width:camera.effective_width || camera.width, height:camera.effective_height || camera.height })
          return latest
        }, []))
      } catch (error) { console.warn('test mode refresh:', error) }
    }
    refresh(); const timer = setInterval(refresh, 2500); return () => clearInterval(timer)
  }, [testMode, testSession])

  useEffect(() => {
    if (!authReady || (authRequired && !principal) || testMode) return
    const t = setInterval(() => { api.getAlertCounts().then(setCounts).catch(console.warn); api.getRecentAnalytics().then(setAnalytics).catch(console.warn) }, 10000)
    return () => clearInterval(t)
  }, [authReady, authRequired, principal, testMode])

  useEffect(() => {
    if (!authReady || (authRequired && !principal) || testMode) return
    const refreshRegistry = () => api.getCameras().then(rows => { setCameras(rows); setProductionCameras(rows) }).catch(console.warn)
    const t = setInterval(refreshRegistry, 60000)
    return () => clearInterval(t)
  }, [authReady, authRequired, principal, testMode])

  const onMessage = useCallback(msg => {
    if (testMode || msg.type !== 'alert') return
    setAlerts(prev => [{ ...msg, _new:true }, ...prev].slice(0, MAX_LIVE_ALERTS))
    setCounts(c => c ? { ...c, total:(c.total || 0)+1, unacknowledged:(c.unacknowledged || 0)+1, [msg.priority?.toLowerCase()]:(c[msg.priority?.toLowerCase()] || 0)+1 } : c)
  }, [testMode])

  const websocketUrl = (() => {
    if (!authReady || (authRequired && !principal)) return null
    const token = localStorage.getItem('sentinel.jwt')
    return token ? `${WS_URL}?access_token=${encodeURIComponent(token)}` : WS_URL
  })()
  useWebSocket(websocketUrl, onMessage)

  const ack = useCallback(async id => {
    try { await api.ackAlert(id); setAlerts(a => a.map(x => (x.alert_id === id || x.id === id) ? { ...x, acknowledged:true } : x)); setCounts(c => c ? { ...c, unacknowledged:Math.max(0,(c.unacknowledged || 1)-1) } : c) }
    catch (e) { console.warn('ack failed:', e) }
  }, [])

  const toggleAlerts = useCallback(() => setAlertsCollapsed(value => { const next=!value; localStorage.setItem('sentinel.alerts.collapsed.v1', String(next)); return next }), [])
  const locateCamera = useCallback(camera => { if (!camera?.id) return; setMapFocus(previous => ({ id:camera.id, nonce:previous.nonce+1 })); navigate('/map') }, [navigate])
  const openCamera = useCallback(camera => { if (!camera?.id) return; setCameraFocus(previous => ({ id:camera.id, nonce:previous.nonce+1 })); navigate('/feeds') }, [navigate])
  const locateRoute = useCallback(sightings => { if (!Array.isArray(sightings) || !sightings.length) return; setVehicleRoute(previous => ({ sightings, nonce:previous.nonce+1 })); navigate('/map') }, [navigate])
  const login = useCallback(async credentials => { const response=await api.login(credentials); localStorage.setItem('sentinel.jwt', response.access_token); setPrincipal(response.user); setAuthReady(true); setAuthConfigError('') }, [])
  const logout = useCallback(async () => { try { await api.logout() } catch {} localStorage.removeItem('sentinel.jwt'); setPrincipal(null); setAlerts([]); setCounts(null); setAuthReady(!authRequired); navigate('/dashboard') }, [authRequired, navigate])
  const onboard = useCallback(async body => { const camera=await api.onboardCamera(body); setCameras(current => [...current,camera].sort((a,b)=>(a.stream_id || 0)-(b.stream_id || 0))); return camera }, [])
  const importCameras = useCallback(async file => { const result=await api.importCameras(file); setCameras(await api.getCameras()); return result }, [])
  const exportDetections = useCallback(async () => { const blob=await api.downloadDetections(); const url=URL.createObjectURL(blob); const link=document.createElement('a'); link.href=url; link.download='sentinel-detections.csv'; link.click(); URL.revokeObjectURL(url) }, [])
  const startTest = useCallback(session => { setTestSession(session); setTestMode(true); setShowTestDiagnostics(false); navigate('/test') }, [navigate])
  const openTest = useCallback(async () => { try { const session=await api.getActiveTestSession(); if (session) return startTest(session) } catch (error) { console.warn('test session lookup:',error) } setShowTestDiagnostics(true); navigate('/test') }, [startTest,navigate])
  const exitTest = useCallback(() => { setTestMode(false); setTestSession(null); setAlerts([]); api.getCameras().then(rows => { setCameras(rows); setProductionCameras(rows) }).catch(console.warn); navigate('/feeds') }, [navigate])
  const clearTest = useCallback(async () => { if (!testSession) return; await api.closeTestSession(testSession.id); exitTest() }, [testSession, exitTest])
  const exportTest = useCallback(async () => { if (!testSession) return; const blob=await api.downloadTestResults(testSession.id); const url=URL.createObjectURL(blob); const link=document.createElement('a'); link.href=url; link.download='sentinel-test-results.csv'; link.click(); URL.revokeObjectURL(url) }, [testSession])

  if (authRequired === null) return <div style={{ minHeight:'100vh',display:'grid',placeItems:'center',background:'var(--bg)',color:'var(--text2)',fontSize:12 }}>Loading Sentinel…</div>
  if (authRequired && !principal) return <LoginModal onLogin={login} error={authConfigError}/>

  const showMap = path === '/map'
  const showFeeds = path === '/dashboard' || path === '/feeds' || path === '/alerts' || path === '/test'
  return <div style={{ display:'flex',flexDirection:'column',height:'100vh',overflow:'hidden' }}>
    <Navbar path={path} onNavigate={navigate} alertCount={counts?.unacknowledged || 0} onSearchOpen={() => { setSearchInit(null); setShowSearch(true); navigate('/investigations') }} onWatchlistOpen={() => setShowWatchlist(true)} onOnboardOpen={() => setShowOnboard(true)} onVendorsOpen={() => setShowVendors(true)} onTestOpen={testEnabled ? () => testMode ? exitTest() : openTest() : null} testMode={testMode} onReportExport={exportDetections} principal={principal} onLogout={logout}/>
    <div style={{ display:'flex',alignItems:'center',gap:8,padding:'6px 14px',background:'var(--surface)',borderBottom:'1px solid var(--border)',flexShrink:0 }}>
      <div style={{ display:'flex',gap:14,fontSize:11 }}><span style={{ color:testMode ? 'var(--accent)':'var(--text2)' }}>{testMode ? 'ISOLATED TEST MODE' : `${cameras.length} cameras`}</span><span style={{ color:'var(--high)',fontWeight:counts?.high ? 700:400 }}>{counts?.high || 0} HIGH</span><span style={{ color:'var(--medium)' }}>{counts?.medium || 0} MED</span><span style={{ color:'var(--low)' }}>{counts?.low || 0} LOW</span></div>
      {testMode && <div style={{ display:'flex',gap:6,marginLeft:10 }}><button onClick={exportTest} style={smallButton}>Export test results</button><button onClick={clearTest} style={{ ...smallButton,color:'var(--high)',borderColor:'var(--high)' }}>Clear test data</button></div>}
      <div style={{ flex:1 }}/>{pipelineStats && <div style={{ display:'flex',alignItems:'center',gap:10,background:'var(--surface2)',borderRadius:6,padding:'3px 10px',border:'1px solid var(--border)',fontSize:10,color:'var(--text2)' }}><span>Pipeline</span>{[['Frames',pipelineStats.raw_frames],['Detect',pipelineStats.detections]].map(([label,value]) => <span key={label}><span style={{ opacity:.6 }}>{label} </span><b style={{ color:label === 'Frames' ? 'var(--green)':'var(--accent)' }}>{(value || 0).toLocaleString()}</b></span>)}</div>}
    </div>
    <div style={{ display:'flex',flex:1,overflow:'hidden' }}>
      <div style={{ flex:1,overflow:'hidden',position:'relative',display:'flex',flexDirection:'column' }}>
        {showMap ? <MapView cameras={productionCameras} alerts={testMode ? [] : alerts} focusCameraId={mapFocus.id} focusNonce={mapFocus.nonce} route={vehicleRoute.sightings} routeFocusNonce={vehicleRoute.nonce}/> : showFeeds ? <div style={{ flex:1,minHeight:0 }}><CameraGrid cameras={cameras} alertsByCam={alertsByCam} analyticsByCam={analyticsByCam} pipelineStats={pipelineStats} onLocate={testMode ? (() => {}) : locateCamera} focusCameraId={cameraFocus.id} focusNonce={cameraFocus.nonce}/></div> : null}
      </div>
      <div style={{ width:alertsCollapsed ? 38:320,transition:'width .18s ease',flexShrink:0,display:'flex',flexDirection:'column',overflow:'hidden' }}><AlertPanel alerts={alerts} onAck={testMode ? (() => {}) : ack} counts={counts} collapsed={alertsCollapsed} onToggle={toggleAlerts} onOpenSearch={async init => { if (init?.tab === 'track' && init.query) { try { const result=await api.searchTrack(init.query); locateRoute(result.sightings || []) } catch(error) { console.warn('journey lookup:', error) } } else { setSearchInit(init); setShowSearch(true); navigate('/investigations') } }}/></div>
    </div>
    {showSearch && <SearchModal init={searchInit} testMode={testMode} testSession={testSession} onClose={() => { setShowSearch(false); setSearchInit(null); navigate('/feeds') }} onViewCamera={openCamera} onLocateCamera={locateCamera} onLocateRoute={locateRoute}/>} 
    {showWatchlist && <WatchlistModal onClose={() => setShowWatchlist(false)}/>} 
    {showOnboard && <OnboardCameraModal onClose={() => setShowOnboard(false)} onSaved={onboard} onImport={importCameras}/>} 
    {showVendors && <VendorModal onClose={() => setShowVendors(false)}/>} 
    {showTestDiagnostics && <TestDiagnosticsModal onClose={() => setShowTestDiagnostics(false)} onStarted={startTest}/>} 
  </div>
}
const smallButton = { padding:'4px 7px', borderRadius:5, border:'1px solid var(--border)', background:'transparent', color:'var(--text2)', cursor:'pointer', fontSize:10 }
