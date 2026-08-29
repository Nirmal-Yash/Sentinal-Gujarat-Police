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
import { Input } from './components/ui/input'
import { Button } from './components/ui/button'

const MAX_LIVE_ALERTS = 300
const VALID_ROUTES = new Set(['/feeds','/map','/alerts','/investigations','/test'])
const normalizePath = path => path === '/dashboard' ? '/feeds' : (VALID_ROUTES.has(path) ? path : '/feeds')
const SearchIcon=()=> <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
const BellIcon=()=> <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 0-3.46 0"/></svg>

function useSpaRoute(){
 const [path,setPath]=useState(()=>normalizePath(window.location.pathname))
 useEffect(()=>{const onPop=()=>setPath(normalizePath(window.location.pathname));window.addEventListener('popstate',onPop);return()=>window.removeEventListener('popstate',onPop)},[])
 const navigate=useCallback(target=>{const next=normalizePath(target);if(window.location.pathname!==next)window.history.pushState({},'',next);setPath(next)},[])
 return [path,navigate]
}

export default function App(){
 const [path,navigate]=useSpaRoute(),[routeMotion,setRouteMotion]=useState(0),[cameras,setCameras]=useState([]),[productionCameras,setProductionCameras]=useState([]),[alerts,setAlerts]=useState([]),[counts,setCounts]=useState(null),[pipelineStats,setPipelineStats]=useState(null),[analytics,setAnalytics]=useState([])
 const [mapFocus,setMapFocus]=useState({id:null,nonce:0}),[cameraFocus,setCameraFocus]=useState({id:null,nonce:0}),[vehicleRoute,setVehicleRoute]=useState({sightings:[],nonce:0}),[alertsCollapsed,setAlertsCollapsed]=useState(()=>localStorage.getItem('sentinel.alerts.collapsed.v1')==='true')
 const [showSearch,setShowSearch]=useState(false),[searchInit,setSearchInit]=useState(null),[showWatchlist,setShowWatchlist]=useState(false),[showOnboard,setShowOnboard]=useState(false),[showVendors,setShowVendors]=useState(false)
 const [authRequired,setAuthRequired]=useState(null),[testEnabled,setTestEnabled]=useState(false),[principal,setPrincipal]=useState(null),[authReady,setAuthReady]=useState(false),[authConfigError,setAuthConfigError]=useState(''),[showTestDiagnostics,setShowTestDiagnostics]=useState(false),[testMode,setTestMode]=useState(false),[testSession,setTestSession]=useState(null)
 const [headerSearch,setHeaderSearch]=useState('')

 useEffect(()=>{setRouteMotion(v=>v+1)},[path])
 useEffect(()=>{const openAlerts=()=>setAlertsCollapsed(false);window.addEventListener('sentinel:open-alerts',openAlerts);return()=>window.removeEventListener('sentinel:open-alerts',openAlerts)},[])
 useEffect(()=>{let active=true;api.getAuthConfig().then(async config=>{if(!active)return;const required=Boolean(config.auth_required);setAuthRequired(required);setTestEnabled(Boolean(config.test_enabled));const token=localStorage.getItem('sentinel.jwt');if(!token){setPrincipal(required?null:{id:null,username:'local-development',role:'SUPERADMIN'});setAuthReady(true);return}try{const me=await api.getMe();if(!active)return;setPrincipal(me);setAuthReady(true);setAuthConfigError('')}catch(error){if(!active)return;localStorage.removeItem('sentinel.jwt');setPrincipal(null);setAuthReady(true);if(required&&error?.message?.startsWith('401'))setAuthConfigError('Your session has expired. Please sign in again.')}}).catch(error=>{if(!active)return;setAuthRequired(true);setTestEnabled(false);setPrincipal(null);setAuthConfigError(error?.message||'Authentication service unavailable');setAuthReady(true)});return()=>{active=false}},[])
 useEffect(()=>{if(path==='/investigations'&&authReady&&!showSearch)setShowSearch(true);if(path==='/test'&&authReady&&testEnabled&&!testMode&&!showTestDiagnostics)setShowTestDiagnostics(true);if(path==='/alerts')setAlertsCollapsed(false);if(path!=='/investigations'&&showSearch&&!searchInit)setShowSearch(false)},[path,authReady,testEnabled,testMode,showTestDiagnostics,showSearch,searchInit])
 const alertsByCam=(alerts||[]).reduce((a,x)=>{if(x.cam_id&&!x.acknowledged)a[x.cam_id]=(a[x.cam_id]||0)+1;return a},{}),analyticsByCam=(analytics||[]).reduce((a,x)=>{if(x.cam_id)a[x.cam_id]=x;return a},{})
 useEffect(()=>{if(!authReady||(authRequired&&!principal)||testMode)return;api.getCameras().then(r=>{setCameras(r);setProductionCameras(r)}).catch(console.warn);api.getAlertCounts().then(setCounts).catch(console.warn);api.getRecentAnalytics().then(setAnalytics).catch(console.warn);api.getAlerts({limit:80}).then(r=>setAlerts(r.map(x=>({...x,_new:false})))).catch(console.warn)},[authReady,authRequired,principal,testMode])
 useEffect(()=>{if(!testMode||!testSession)return;const refresh=async()=>{try{const [tc,result,status]=await Promise.all([api.getTestCameras(testSession.id),api.getTestResults(testSession.id),api.getTestStatus(testSession.id)]);setCameras(tc);setAlerts((result.alerts||[]).map(a=>({...a,id:a.id,alert_id:a.id,cam_id:null,_new:false})));setCounts({total:status.alerts||0,unacknowledged:status.alerts||0,high:0,medium:0,low:status.alerts||0});setPipelineStats({raw_frames:status.frames_processed||0,detections:status.detections||0});setAnalytics((result.detections||[]).filter(x=>x.plate_text).reduce((latest,item)=>{const cam=tc.find(v=>v.stream_id===item.stream_id),cam_id=cam?.id;if(cam_id&&!latest.some(v=>v.cam_id===cam_id))latest.push({cam_id,plate_text:item.plate_text,confidence:item.confidence,bbox:item.bbox,width:cam.effective_width||cam.width,height:cam.effective_height||cam.height});return latest},[]))}catch(error){console.warn('test mode refresh:',error)}};refresh();const timer=setInterval(refresh,2500);return()=>clearInterval(timer)},[testMode,testSession])
 useEffect(()=>{if(!authReady||(authRequired&&!principal)||testMode)return;const timer=setInterval(()=>{api.getAlertCounts().then(setCounts).catch(console.warn);api.getRecentAnalytics().then(setAnalytics).catch(console.warn)},10000);return()=>clearInterval(timer)},[authReady,authRequired,principal,testMode])
 useEffect(()=>{if(!authReady||(authRequired&&!principal)||testMode)return;const refresh=()=>api.getCameras().then(r=>{setCameras(r);setProductionCameras(r)}).catch(console.warn);const timer=setInterval(refresh,60000);return()=>clearInterval(timer)},[authReady,authRequired,principal,testMode])
 const onMessage=useCallback(msg=>{if(testMode||msg.type!=='alert')return;setAlerts(p=>[{...msg,_new:true},...p].slice(0,MAX_LIVE_ALERTS));setCounts(c=>c?{...c,total:(c.total||0)+1,unacknowledged:(c.unacknowledged||0)+1,[msg.priority?.toLowerCase()]:(c[msg.priority?.toLowerCase()]||0)+1}:c)},[testMode])
 const websocketUrl=(()=>{if(!authReady||(authRequired&&!principal))return null;const token=localStorage.getItem('sentinel.jwt');return token?`${WS_URL}?access_token=${encodeURIComponent(token)}`:WS_URL})();useWebSocket(websocketUrl,onMessage)
 const ack=useCallback(async id=>{try{await api.ackAlert(id);setAlerts(a=>a.map(x=>(x.alert_id===id||x.id===id)?{...x,acknowledged:true,status:'ACKNOWLEDGED'}:x));setCounts(c=>c?{...c,unacknowledged:Math.max(0,(c.unacknowledged||1)-1)}:c)}catch(e){console.warn('ack failed:',e)}},[])
 const toggleAlerts=useCallback(()=>setAlertsCollapsed(v=>{const n=!v;localStorage.setItem('sentinel.alerts.collapsed.v1',String(n));return n}),[])
 const locateCamera=useCallback(c=>{if(!c?.id)return;setMapFocus(p=>({id:c.id,nonce:p.nonce+1}));navigate('/map')},[navigate]),openCamera=useCallback(c=>{if(!c?.id)return;setCameraFocus(p=>({id:c.id,nonce:p.nonce+1}));navigate('/feeds')},[navigate]),locateRoute=useCallback(s=>{if(!Array.isArray(s)||!s.length)return;setVehicleRoute(p=>({sightings:s,nonce:p.nonce+1}));navigate('/map')},[navigate])
 const openSearch=useCallback((query='')=>{setSearchInit(query?{tab:'camera',query}:null);setShowSearch(true);navigate('/investigations')},[navigate])
 const login=useCallback(async credentials=>{const response=await api.login(credentials);localStorage.setItem('sentinel.jwt',response.access_token);setPrincipal(response.user);setAuthReady(true);setAuthConfigError('')},[])
 const logout=useCallback(async()=>{try{await api.logout()}catch{}localStorage.removeItem('sentinel.jwt');setPrincipal(null);setAlerts([]);setCounts(null);setAuthReady(!authRequired);navigate('/feeds')},[authRequired,navigate])
 const onboard=useCallback(async body=>{const camera=await api.onboardCamera(body);setCameras(c=>[...c,camera].sort((a,b)=>(a.stream_id||0)-(b.stream_id||0)));return camera},[]),importCameras=useCallback(async file=>{const r=await api.importCameras(file);setCameras(await api.getCameras());return r},[])
 const exportDetections=useCallback(async()=>{const blob=await api.downloadDetections(),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='sentinel-detections.csv';link.click();URL.revokeObjectURL(url)},[])
 const startTest=useCallback(session=>{setTestSession(session);setTestMode(true);setShowTestDiagnostics(false);navigate('/test')},[navigate]),openTest=useCallback(async()=>{try{const session=await api.getActiveTestSession();if(session)return startTest(session)}catch(e){console.warn('test session lookup:',e)}setShowTestDiagnostics(true);navigate('/test')},[startTest,navigate]),exitTest=useCallback(()=>{setTestMode(false);setTestSession(null);setAlerts([]);api.getCameras().then(r=>{setCameras(r);setProductionCameras(r)}).catch(console.warn);navigate('/feeds')},[navigate]),clearTest=useCallback(async()=>{if(!testSession)return;await api.closeTestSession(testSession.id);exitTest()},[testSession,exitTest]),exportTest=useCallback(async()=>{if(!testSession)return;const blob=await api.downloadTestResults(testSession.id),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='sentinel-test-results.csv';link.click();URL.revokeObjectURL(url)},[testSession])
 const submitHeaderSearch=useCallback(event=>{event.preventDefault();openSearch(headerSearch.trim())},[openSearch,headerSearch])
 if(authRequired===null)return <div style={{minHeight:'100vh',display:'grid',placeItems:'center',background:'var(--bg)',color:'var(--text2)',fontSize:12}}>Loading Sentinel…</div>
 if(authRequired&&!principal)return <LoginModal onLogin={login} error={authConfigError}/>
 const showMap=path==='/map',showFeeds=path==='/feeds'||path==='/alerts'||path==='/test'
 return <div className="sentinel-shell">
   <Navbar path={path} onNavigate={navigate} alertCount={counts?.unacknowledged||0} onSearchOpen={openSearch} onWatchlistOpen={()=>setShowWatchlist(true)} onOnboardOpen={()=>setShowOnboard(true)} onVendorsOpen={()=>setShowVendors(true)} onTestOpen={testEnabled?()=>testMode?exitTest():openTest():null} testMode={testMode} principal={principal} onLogout={logout}/>
   <main className="sentinel-main">
     <header className="sentinel-topbar">
       <div className="sentinel-topbar-title-wrap"><div className="sentinel-topbar-title">{path==='/map'?'GIS Command Map':path==='/investigations'?'Vehicle Investigation':path==='/alerts'?'Alert Operations':path==='/test'?'Demonstration Environment':'Live Monitoring'}</div><div className="sentinel-topbar-sub">Statewide CCTV Intelligence</div></div>
       <form className="sentinel-search-wrap" onSubmit={submitHeaderSearch}><span className="sentinel-search-icon"><SearchIcon/></span><Input value={headerSearch} onChange={e=>setHeaderSearch(e.target.value)} className="sentinel-search-input" placeholder="Search camera, plate or track…" aria-label="Search camera, plate or track"/><span className="sentinel-search-hint">Enter</span></form>
       <div className="sentinel-topbar-actions"><span className="sentinel-status"><span className="sentinel-live-pulse"/>SYSTEM ONLINE</span>{counts?.unacknowledged>0&&<Button variant="ghost" size="sm" title="Open alerts" onClick={()=>{navigate('/alerts');setAlertsCollapsed(false)}}><BellIcon/><span>{Math.min(counts.unacknowledged,99)}</span></Button>}<div className="sentinel-clock">{new Date().toLocaleTimeString('en-IN',{hour12:false})}</div></div>
     </header>
     <div className={routeMotion%2?'sentinel-route sentinel-route-a':'sentinel-route sentinel-route-b'} style={{display:'flex',flex:1,minHeight:0,overflow:'hidden'}}>
       <div style={{flex:1,minWidth:0,overflow:'hidden',position:'relative',display:'flex',flexDirection:'column'}}>{showMap?<MapView cameras={productionCameras} alerts={testMode?[]:alerts} focusCameraId={mapFocus.id} focusNonce={mapFocus.nonce} route={vehicleRoute.sightings} routeFocusNonce={vehicleRoute.nonce}/>:showFeeds?<div style={{flex:1,minHeight:0}}><CameraGrid cameras={cameras} alertsByCam={alertsByCam} analyticsByCam={analyticsByCam} pipelineStats={pipelineStats} onLocate={testMode?()=>{}:locateCamera} focusCameraId={cameraFocus.id} focusNonce={cameraFocus.nonce}/></div>:<div style={{flex:1}}/>}</div>
       <div style={{width:alertsCollapsed?38:320,transition:'width .2s ease',flexShrink:0,display:'flex',flexDirection:'column',overflow:'hidden'}}><AlertPanel alerts={alerts} onAck={testMode?()=>{}:ack} counts={counts} collapsed={alertsCollapsed} onToggle={toggleAlerts} onOpenSearch={async init=>{if(init?.tab==='track'&&init.query){try{const result=await api.searchTrack(init.query);locateRoute(result.sightings||[])}catch(error){console.warn('journey lookup:',error)}}else openSearch(init?.query||'')}}/></div>
     </div>
   </main>
   {showSearch&&<SearchModal init={searchInit} testMode={testMode} testSession={testSession} onClose={()=>{setShowSearch(false);setSearchInit(null);navigate('/feeds')}} onViewCamera={openCamera} onLocateCamera={locateCamera} onLocateRoute={locateRoute}/>} 
   {showWatchlist&&<WatchlistModal onClose={()=>setShowWatchlist(false)}/>} {showOnboard&&<OnboardCameraModal onClose={()=>setShowOnboard(false)} onSaved={onboard} onImport={importCameras}/>} {showVendors&&<VendorModal onClose={()=>setShowVendors(false)}/>} {showTestDiagnostics&&<TestDiagnosticsModal onClose={()=>{setShowTestDiagnostics(false);navigate('/feeds')}} onStarted={startTest}/>} 
 </div>
}
