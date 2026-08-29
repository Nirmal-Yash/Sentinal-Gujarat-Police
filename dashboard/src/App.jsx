import { useCallback, useEffect, useRef, useState } from 'react'
import { api, WS_URL } from './api/client'
import { useWebSocket } from './hooks/useWebSocket'
import Navbar from './components/Navbar'
import CameraGrid from './components/CameraGrid'
import MapView from './components/MapView'
import AlertPanel from './components/AlertPanel'
import SearchInvestigationModal from './components/SearchInvestigationModal'
import WatchlistModal from './components/WatchlistModal'
import OnboardCameraModal from './components/OnboardCameraModal'
import LoginModal from './components/LoginModal'
import VendorModal from './components/VendorModal'
import TestDiagnosticsModal from './components/TestDiagnosticsModal'
import { Input } from './components/ui/input'
import { Button } from './components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription, SheetClose, SheetBody } from './components/ui/sheet'
import { normalizePath } from './routeState.mjs'

const TEST_SESSION_KEY='sentinel.test.session.v1', RETURN_ROUTE_KEY='sentinel.overlay.return.route.v1', MAX_LIVE_ALERTS=300
const readSession=()=>{try{return sessionStorage.getItem(TEST_SESSION_KEY)}catch{return null}}
const writeSession=v=>{try{v?sessionStorage.setItem(TEST_SESSION_KEY,v):sessionStorage.removeItem(TEST_SESSION_KEY)}catch{}}
const SearchIcon=()=> <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
const BellIcon=()=> <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 5-2.2 7.3-3 8.5h18C20.2 15.3 18 13 18 8Z"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/></svg>
const CloseIcon=()=> <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="m18 6-12 12M6 6l12 12"/></svg>

function useSpaRoute(){
  const [path,setPath]=useState(()=>normalizePath(window.location.pathname))
  useEffect(()=>{const onPop=()=>setPath(normalizePath(window.location.pathname));window.addEventListener('popstate',onPop);return()=>window.removeEventListener('popstate',onPop)},[])
  const navigate=useCallback((target,{replace=false}={})=>{const next=normalizePath(target);const current=normalizePath(window.location.pathname);if(current!==next){window.history[replace?'replaceState':'pushState']({...window.history.state,sentinelRoute:next},'',next)}setPath(next)},[])
  return [path,navigate]
}

export default function App(){
  const [path,navigate]=useSpaRoute(),[now,setNow]=useState(()=>new Date()),[routeMotion,setRouteMotion]=useState(0)
  const [cameras,setCameras]=useState([]),[productionCameras,setProductionCameras]=useState([]),[alerts,setAlerts]=useState([]),[counts,setCounts]=useState(null),[pipelineStats,setPipelineStats]=useState(null),[analytics,setAnalytics]=useState([])
  const [mapFocus,setMapFocus]=useState({id:null,nonce:0}),[cameraFocus,setCameraFocus]=useState({id:null,nonce:0}),[vehicleRoute,setVehicleRoute]=useState({sightings:[],nonce:0})
  const [alertsOpen,setAlertsOpen]=useState(false),[showSearch,setShowSearch]=useState(false),[searchInit,setSearchInit]=useState(null),[showWatchlist,setShowWatchlist]=useState(false),[showOnboard,setShowOnboard]=useState(false),[showVendors,setShowVendors]=useState(false)
  const [authRequired,setAuthRequired]=useState(null),[testEnabled,setTestEnabled]=useState(false),[principal,setPrincipal]=useState(null),[authReady,setAuthReady]=useState(false),[authError,setAuthError]=useState('')
  const [showTestDiagnostics,setShowTestDiagnostics]=useState(false),[testMode,setTestMode]=useState(false),[testSession,setTestSession]=useState(null),[headerSearch,setHeaderSearch]=useState('')
  const previousPath=useRef('/feeds')

  useEffect(()=>{setRouteMotion(v=>v+1);previousPath.current=path},[path])
  useEffect(()=>{const timer=setInterval(()=>setNow(new Date()),1000);return()=>clearInterval(timer)},[])
  useEffect(()=>{let active=true;api.getAuthConfig().then(async config=>{if(!active)return;const required=Boolean(config.auth_required);setAuthRequired(required);setTestEnabled(Boolean(config.test_enabled));const token=localStorage.getItem('sentinel.jwt');if(!token){setPrincipal(required?null:{id:null,username:'local-development',role:'SUPERADMIN'});setAuthReady(true);return}try{const me=await api.getMe();if(active){setPrincipal(me);setAuthReady(true);setAuthError('')}}catch(error){if(active){localStorage.removeItem('sentinel.jwt');setPrincipal(null);setAuthReady(true);setAuthError(error?.message?.startsWith('401')?'Your session has expired. Please sign in again.':(error?.message||'Authentication service unavailable'))}}}).catch(error=>{if(active){setAuthRequired(true);setTestEnabled(false);setPrincipal(null);setAuthReady(true);setAuthError(error?.message||'Authentication service unavailable')}});return()=>{active=false}},[])
  useEffect(()=>{if(!authReady)return;setShowSearch(path==='/investigations');if(path!=='/investigations')setSearchInit(null)},[path,authReady])
  useEffect(()=>{setAlertsOpen(path==='/alerts')},[path])
  useEffect(()=>{if(!authReady||!testEnabled||path!=='/test'||testMode||showTestDiagnostics)return;let active=true;(async()=>{try{const session=await api.getActiveTestSession();const stored=readSession();if(active&&session&&stored&&String(stored)===String(session.id)){setTestSession(session);setTestMode(true);return}}catch(error){console.warn('test session restore:',error)}if(active)setShowTestDiagnostics(true)})();return()=>{active=false}},[authReady,testEnabled,path,testMode,showTestDiagnostics])

  const alertsByCam=(alerts||[]).reduce((a,x)=>{if(x.cam_id&&!x.acknowledged)a[x.cam_id]=(a[x.cam_id]||0)+1;return a},{}),analyticsByCam=(analytics||[]).reduce((a,x)=>{if(x.cam_id)a[x.cam_id]=x;return a},{})
  useEffect(()=>{if(!authReady||(authRequired&&!principal)||testMode)return;Promise.all([api.getCameras(),api.getAlertCounts(),api.getRecentAnalytics(),api.getAlerts({limit:80})]).then(([cams,c,an,al])=>{setCameras(cams);setProductionCameras(cams);setCounts(c);setAnalytics(an);setAlerts(al.map(x=>({...x,_new:false})))}).catch(console.warn)},[authReady,authRequired,principal,testMode])
  useEffect(()=>{if(!authReady||(authRequired&&!principal)||testMode)return;const timer=setInterval(()=>Promise.all([api.getAlertCounts(),api.getRecentAnalytics()]).then(([c,a])=>{setCounts(c);setAnalytics(a)}).catch(()=>{}),10000);return()=>clearInterval(timer)},[authReady,authRequired,principal,testMode])
  useEffect(()=>{if(!authReady||(authRequired&&!principal)||testMode)return;const timer=setInterval(()=>api.getCameras().then(r=>{setCameras(r);setProductionCameras(r)}).catch(()=>{}),60000);return()=>clearInterval(timer)},[authReady,authRequired,principal,testMode])
  useEffect(()=>{if(!testMode||!testSession)return;let active=true;const refresh=async()=>{try{const [tc,result,status]=await Promise.all([api.getTestCameras(testSession.id),api.getTestResults(testSession.id),api.getTestStatus(testSession.id)]);if(!active)return;setCameras(tc);setAlerts(result.alerts||[]);setCounts({total:status.alerts||0,unacknowledged:status.alerts||0,high:0,medium:0,low:status.alerts||0});setPipelineStats({raw_frames:status.frames_processed||0,detections:status.detections||0});setAnalytics((result.detections||[]).filter(x=>x.plate_text).reduce((latest,item)=>{const cam=tc.find(v=>v.stream_id===item.stream_id);if(cam&&!latest.some(v=>v.cam_id===cam.id))latest.push({cam_id:cam.id,plate_text:item.plate_text,confidence:item.confidence,bbox:item.bbox,width:cam.effective_width||cam.width,height:cam.effective_height||cam.height});return latest},[]))}catch(error){if(active)console.warn('test mode refresh:',error)}};refresh();const timer=setInterval(refresh,2500);return()=>{active=false;clearInterval(timer)}},[testMode,testSession])

  const onMessage=useCallback(msg=>{if(testMode||msg.type!=='alert')return;setAlerts(v=>[{...msg,_new:true},...v].slice(0,MAX_LIVE_ALERTS));setCounts(c=>c?{...c,total:(c.total||0)+1,unacknowledged:(c.unacknowledged||0)+1}:c)},[testMode])
  const websocketUrl=!authReady||(authRequired&&!principal)?null:(()=>{const token=localStorage.getItem('sentinel.jwt');return token?`${WS_URL}?access_token=${encodeURIComponent(token)}`:WS_URL})()
  useWebSocket(websocketUrl,onMessage)
  const ack=useCallback(async id=>{try{await api.ackAlert(id);setAlerts(v=>v.map(x=>(x.alert_id===id||x.id===id)?{...x,acknowledged:true,status:'ACKNOWLEDGED'}:x));setCounts(c=>c?{...c,unacknowledged:Math.max(0,(c.unacknowledged||1)-1)}:c)}catch(error){console.warn('ack failed:',error)}},[])
  const openCamera=useCallback(c=>{if(!c?.id)return;setCameraFocus(v=>({id:c.id,nonce:v.nonce+1}));navigate('/feeds')},[navigate])
  const locateCamera=useCallback(c=>{if(!c?.id)return;setMapFocus(v=>({id:c.id,nonce:v.nonce+1}));navigate('/map')},[navigate])
  const locateRoute=useCallback(s=>{if(!Array.isArray(s)||!s.length)return;setVehicleRoute(v=>({sightings:s,nonce:v.nonce+1}));navigate('/map')},[navigate])
  const openSearch=useCallback((query='')=>{setSearchInit(query?{tab:'camera',query}:null);setShowSearch(true);try{sessionStorage.setItem(RETURN_ROUTE_KEY,path)}catch{}navigate('/investigations')},[navigate,path])
  const closeSearch=useCallback(()=>{setShowSearch(false);setSearchInit(null);let target='/feeds';try{target=sessionStorage.getItem(RETURN_ROUTE_KEY)||target;sessionStorage.removeItem(RETURN_ROUTE_KEY)}catch{}navigate(target)},[navigate])
  const openAlerts=useCallback(()=>{try{sessionStorage.setItem(RETURN_ROUTE_KEY,path)}catch{};setAlertsOpen(true);navigate('/alerts')},[path,navigate])
  const closeAlerts=useCallback(()=>{setAlertsOpen(false);let target='/feeds';try{target=sessionStorage.getItem(RETURN_ROUTE_KEY)||target;sessionStorage.removeItem(RETURN_ROUTE_KEY)}catch{}navigate(target)},[navigate])
  const login=useCallback(async credentials=>{const r=await api.login(credentials);localStorage.setItem('sentinel.jwt',r.access_token);setPrincipal(r.user);setAuthReady(true);setAuthError('')},[])
  const logout=useCallback(async()=>{try{await api.logout()}catch{}localStorage.removeItem('sentinel.jwt');writeSession(null);setPrincipal(null);setAlerts([]);setCounts(null);setTestMode(false);setTestSession(null);navigate('/feeds')},[navigate])
  const onboard=useCallback(async body=>{const c=await api.onboardCamera(body);setCameras(v=>[...v,c].sort((a,b)=>(a.stream_id||0)-(b.stream_id||0)));setProductionCameras(v=>[...v,c].sort((a,b)=>(a.stream_id||0)-(b.stream_id||0)));return c},[])
  const importCameras=useCallback(async file=>{const r=await api.importCameras(file);const cams=await api.getCameras();setCameras(cams);setProductionCameras(cams);return r},[])
  const startTest=useCallback(session=>{if(!session?.id)return;writeSession(session.id);setTestSession(session);setTestMode(true);setShowTestDiagnostics(false);navigate('/test')},[navigate])
  const openTest=useCallback(async()=>{try{const s=await api.getActiveTestSession();if(s)return startTest(s)}catch(error){console.warn('test session lookup:',error)}setShowTestDiagnostics(true);navigate('/test')},[navigate,startTest])
  const exitTest=useCallback(()=>{writeSession(null);setTestMode(false);setTestSession(null);setAlerts([]);setCounts(null);setPipelineStats(null);setAnalytics([]);api.getCameras().then(r=>{setCameras(r);setProductionCameras(r)}).catch(()=>{});navigate('/feeds')},[navigate])
  const submitHeaderSearch=useCallback(e=>{e.preventDefault();openSearch(headerSearch.trim())},[openSearch,headerSearch])

  if(authRequired===null)return <div className="sentinel-loading-screen">Loading Sentinel…</div>
  if(authRequired&&!principal)return <LoginModal onLogin={login} error={authError}/>
  const showMap=path==='/map',showFeeds=path==='/feeds'||path==='/alerts'||path==='/test'
  const title=path==='/map'?'GIS Map':path==='/investigations'?'Investigate':path==='/alerts'?'Alerts':path==='/test'?'Test Mode':'Monitor'
  return <div className="sentinel-shell"><Navbar path={path} onNavigate={navigate} alertCount={counts?.unacknowledged||0} onWatchlistOpen={()=>setShowWatchlist(true)} onOnboardOpen={()=>setShowOnboard(true)} onVendorsOpen={()=>setShowVendors(true)} onTestOpen={testEnabled?()=>testMode?exitTest():openTest():null} testMode={testMode} principal={principal} onLogout={logout} onAlertsOpen={openAlerts}/><main className="sentinel-main"><header className="sentinel-topbar"><div className="sentinel-topbar-title">{title}</div><form className="sentinel-search-wrap" onSubmit={submitHeaderSearch}><span className="sentinel-search-icon"><SearchIcon/></span><Input value={headerSearch} onChange={e=>setHeaderSearch(e.target.value)} className="sentinel-search-input" placeholder="Search camera, plate or track" aria-label="Search camera, plate or track"/></form><div className="sentinel-topbar-actions"><div className="sentinel-status"><span className="sentinel-live-pulse"/>LIVE</div><Button variant="outline" size="sm" className="sentinel-alerts-trigger" title="Open alerts" aria-label="Open alerts" onClick={openAlerts}><BellIcon/>{counts?.unacknowledged>0&&<span className="sentinel-alert-count">{Math.min(counts.unacknowledged,99)}</span>}</Button><time className="sentinel-clock" dateTime={now.toISOString()}>{now.toLocaleTimeString('en-IN',{hour12:false})}</time></div></header><div className={`sentinel-route sentinel-route-${routeMotion%2?'b':'a'}`} style={{display:'flex',flex:1,minHeight:0,overflow:'hidden'}}><div style={{flex:1,minWidth:0,overflow:'hidden',position:'relative',display:'flex',flexDirection:'column'}}>{showMap?<MapView cameras={productionCameras} alerts={testMode?[]:alerts} focusCameraId={mapFocus.id} focusNonce={mapFocus.nonce} route={vehicleRoute.sightings} routeFocusNonce={vehicleRoute.nonce}/>:showFeeds?<div style={{flex:1,minHeight:0}}><CameraGrid cameras={cameras} alertsByCam={alertsByCam} analyticsByCam={analyticsByCam} pipelineStats={pipelineStats} onLocate={testMode?undefined:locateCamera} focusCameraId={cameraFocus.id} focusNonce={cameraFocus.nonce}/></div>:null}</div></div></main><Sheet open={alertsOpen} onOpenChange={open=>open?setAlertsOpen(true):closeAlerts()}><SheetContent side="right"><SheetHeader><div><SheetTitle>Alerts</SheetTitle><SheetDescription>Live alert queue and operator actions</SheetDescription></div><SheetClose onClose={closeAlerts}><CloseIcon/></SheetClose></SheetHeader><SheetBody><AlertPanel alerts={alerts} onAck={testMode?undefined:ack} counts={counts} collapsed={false} onToggle={closeAlerts} onOpenSearch={async init=>{if(init?.tab==='track'&&init.query){try{const r=await api.searchTrack(init.query);locateRoute(r.sightings||[])}catch(error){console.warn('journey lookup:',error)}}else openSearch(init?.query||'')}} isTest={testMode} testSessionId={testSession?.id}/></SheetBody></SheetContent></Sheet>{showSearch&&<SearchInvestigationModal init={searchInit} testMode={testMode} testSession={testSession} onClose={closeSearch} onViewCamera={openCamera} onLocateCamera={locateCamera} onLocateRoute={locateRoute}/>} {showWatchlist&&<WatchlistModal onClose={()=>setShowWatchlist(false)}/>} {showOnboard&&<OnboardCameraModal onClose={()=>setShowOnboard(false)} onSaved={onboard} onImport={importCameras}/>} {showVendors&&<VendorModal onClose={()=>setShowVendors(false)}/>} {showTestDiagnostics&&<TestDiagnosticsModal onClose={()=>{setShowTestDiagnostics(false);navigate('/feeds')}} onStarted={startTest}/>}</div>
}
