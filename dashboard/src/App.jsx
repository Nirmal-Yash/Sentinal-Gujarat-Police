import { useCallback, useEffect, useRef, useState } from 'react'
import { api, WS_URL } from './api/client'
import { useWebSocket } from './hooks/useWebSocket'
import Navbar from './components/Navbar'
import CameraGrid from './components/CameraGrid'
import MapView from './components/MapView'
import InvestigationPanel from './components/InvestigationPanel'
import WatchlistModal from './components/WatchlistModal'
import OnboardCameraModal from './components/OnboardCameraModal'
import LoginModal from './components/LoginModal'
import VendorModal from './components/VendorModal'
import TestDiagnosticsModal from './components/TestDiagnosticsModal'
import CameraSearch from './components/CameraSearch'
import MapSearch from './components/MapSearch'
import NotificationBell from './components/NotificationBell'
import AlertsPage from './components/AlertsPage'
import { normalizePath } from './routeState.mjs'

const TEST_SESSION_KEY='sentinel.test.session.v1', RETURN_ROUTE_KEY='sentinel.overlay.return.route.v1', AUTH_ROUTE_KEY='sentinel.auth.return.route.v1', MAX_LIVE_ALERTS=300
const readSession=()=>{try{return sessionStorage.getItem(TEST_SESSION_KEY)}catch{return null}}
const writeSession=v=>{try{v?sessionStorage.setItem(TEST_SESSION_KEY,v):sessionStorage.removeItem(TEST_SESSION_KEY)}catch{}}
const readAuthRoute=()=>{try{return sessionStorage.getItem(AUTH_ROUTE_KEY)||'/feeds'}catch{return'/feeds'}}
const writeAuthRoute=v=>{try{v?sessionStorage.setItem(AUTH_ROUTE_KEY,v):sessionStorage.removeItem(AUTH_ROUTE_KEY)}catch{}}

function useSpaRoute(){
 const [path,setPath]=useState(()=>normalizePath(window.location.pathname))
 useEffect(()=>{const onPop=()=>setPath(normalizePath(window.location.pathname));window.addEventListener('popstate',onPop);return()=>window.removeEventListener('popstate',onPop)},[])
 const navigate=useCallback((target,{replace=false}={})=>{const next=normalizePath(target),current=normalizePath(window.location.pathname);if(current!==next){window.history[replace?'replaceState':'pushState']({...window.history.state,sentinelRoute:next},'',next);window.dispatchEvent(new PopStateEvent('popstate'))}else setPath(next)},[])
 return[path,navigate]
}

export default function App(){
 const [path,navigate]=useSpaRoute(),[now,setNow]=useState(()=>new Date()),[routeMotion,setRouteMotion]=useState(0)
 const [cameras,setCameras]=useState([]),[productionCameras,setProductionCameras]=useState([]),[alerts,setAlerts]=useState([]),[counts,setCounts]=useState(null),[pipelineStats,setPipelineStats]=useState(null),[analytics,setAnalytics]=useState([])
 const [mapFocus,setMapFocus]=useState({id:null,nonce:0}),[cameraFocus,setCameraFocus]=useState({id:null,nonce:0}),[vehicleRoute,setVehicleRoute]=useState({sightings:[],nonce:0})
 const [showSearch,setShowSearch]=useState(false),[searchInit,setSearchInit]=useState(null),[showWatchlist,setShowWatchlist]=useState(false),[showOnboard,setShowOnboard]=useState(false),[showVendors,setShowVendors]=useState(false)
 const [authRequired,setAuthRequired]=useState(null),[testEnabled,setTestEnabled]=useState(false),[principal,setPrincipal]=useState(null),[authReady,setAuthReady]=useState(false),[authError,setAuthError]=useState('')
 const [showTestDiagnostics,setShowTestDiagnostics]=useState(false),[testMode,setTestMode]=useState(false),[testSession,setTestSession]=useState(null),[headerSearch,setHeaderSearch]=useState('')
 useEffect(()=>{setRouteMotion(v=>v+1)},[path])
 useEffect(()=>{const timer=setInterval(()=>setNow(new Date()),1000);return()=>clearInterval(timer)},[])
 useEffect(()=>{let active=true;api.getAuthConfig().then(async config=>{if(!active)return;const required=Boolean(config.auth_required);setAuthRequired(required);setTestEnabled(Boolean(config.test_enabled));const token=localStorage.getItem('sentinel.jwt');if(!token){setPrincipal(required?null:{id:null,username:'local-development',role:'SUPERADMIN'});setAuthReady(true);return}try{const me=await api.getMe();if(active){setPrincipal(me);setAuthReady(true);setAuthError('')}}catch(error){if(active){localStorage.removeItem('sentinel.jwt');setPrincipal(null);setAuthReady(true);setAuthError(error?.message?.startsWith('401')?'Your session has expired. Please sign in again.':(error?.message||'Authentication service unavailable'))}}}).catch(error=>{if(active){setAuthRequired(true);setTestEnabled(false);setPrincipal(null);setAuthReady(true);setAuthError(error?.message||'Authentication service unavailable')}});return()=>{active=false}},[])
 useEffect(()=>{if(!authReady||!authRequired||principal)return;const token=localStorage.getItem('sentinel.jwt');if(!token)writeAuthRoute(path)},[authReady,authRequired,principal,path])
 useEffect(()=>{if(!authReady||!testEnabled||path!=='/test'||testMode||showTestDiagnostics||!principal)return;let active=true;(async()=>{try{const session=await api.getActiveTestSession();const stored=readSession();if(active&&session&&stored&&String(stored)===String(session.id)){setTestSession(session);setTestMode(true);return}}catch(error){console.warn('test session restore:',error)}if(active)setShowTestDiagnostics(true)})();return()=>{active=false}},[authReady,testEnabled,path,testMode,showTestDiagnostics,principal])
 useEffect(()=>{if(!authReady||(authRequired&&!principal)||testMode)return;Promise.all([api.getCameras(),api.getAlertCounts(),api.getRecentAnalytics(),api.getAlerts({limit:300})]).then(([cams,c,an,al])=>{setCameras(cams);setProductionCameras(cams);setCounts(c);setAnalytics(an);setAlerts(al.map(x=>({...x,_new:false})))}).catch(console.warn)},[authReady,authRequired,principal,testMode])
 useEffect(()=>{if(!authReady||(authRequired&&!principal)||testMode)return;const timer=setInterval(()=>Promise.all([api.getAlertCounts(),api.getRecentAnalytics()]).then(([c,a])=>{setCounts(c);setAnalytics(a)}).catch(()=>{}),10000);return()=>clearInterval(timer)},[authReady,authRequired,principal,testMode])
 useEffect(()=>{if(!authReady||(authRequired&&!principal)||testMode)return;const timer=setInterval(()=>api.getCameras().then(r=>{setCameras(r);setProductionCameras(r)}).catch(()=>{}),60000);return()=>clearInterval(timer)},[authReady,authRequired,principal,testMode])
 useEffect(()=>{if(!testMode||!testSession)return;let active=true;const refresh=async()=>{try{const[tc,result,status]=await Promise.all([api.getTestCameras(testSession.id),api.getTestResults(testSession.id),api.getTestStatus(testSession.id)]);if(!active)return;setCameras(tc);setAlerts(result.alerts||[]);setCounts({total:status.alerts||0,unacknowledged:status.alerts||0,high:0,medium:0,low:status.alerts||0});setPipelineStats({raw_frames:status.frames_processed||0,detections:status.detections||0});setAnalytics((result.detections||[]).filter(x=>x.plate_text).reduce((latest,item)=>{const cam=tc.find(v=>v.stream_id===item.stream_id);if(cam&&!latest.some(v=>v.cam_id===cam.id))latest.push({cam_id:cam.id,plate_text:item.plate_text,confidence:item.confidence,bbox:item.bbox,width:cam.effective_width||cam.width,height:cam.effective_height||cam.height});return latest},[]))}catch(error){if(active)console.warn('test mode refresh:',error)}};refresh();const timer=setInterval(refresh,2500);return()=>{active=false;clearInterval(timer)}},[testMode,testSession])
 const alertsByCam=(alerts||[]).reduce((a,x)=>{if(x.cam_id&&!x.acknowledged)a[x.cam_id]=(a[x.cam_id]||0)+1;return a},{}),analyticsByCam=(analytics||[]).reduce((a,x)=>{if(x.cam_id)a[x.cam_id]=x;return a},{})
 const onMessage=useCallback(msg=>{if(testMode||msg.type!=='alert')return;setAlerts(v=>[{...msg,_new:true},...v].slice(0,MAX_LIVE_ALERTS));setCounts(c=>c?{...c,total:(c.total||0)+1,unacknowledged:(c.unacknowledged||0)+1}:c)},[testMode])
 const websocketUrl=!authReady||(authRequired&&!principal)?null:(()=>{const token=localStorage.getItem('sentinel.jwt');return token?`${WS_URL}?access_token=${encodeURIComponent(token)}`:WS_URL})()
 useWebSocket(websocketUrl,onMessage)
 const transitionAlert=useCallback(async(alert,target)=>{const id=alert.id||alert.alert_id;if(!id)return;const result=testMode&&testSession?await api.transitionTestAlert(testSession.id,id,target):await api.transitionAlert(id,target);setAlerts(v=>v.map(x=>(x.id||x.alert_id)===id?{...x,status:result.status||target,acknowledged:target!=='NEW'}:x));setCounts(c=>c&&target==='ACKNOWLEDGED'?{...c,unacknowledged:Math.max(0,(c.unacknowledged||1)-1)}:c)},[testMode,testSession])
 const ack=useCallback(id=>transitionAlert({id},'ACKNOWLEDGED'),[transitionAlert])
 const openCamera=useCallback(c=>{if(!c?.id)return;setCameraFocus(v=>({id:c.id,nonce:v.nonce+1}));navigate('/feeds')},[navigate])
 const locateCamera=useCallback(c=>{if(!c?.id)return;setMapFocus(v=>({id:c.id,nonce:v.nonce+1}));navigate('/map')},[navigate])
 const locateRoute=useCallback(s=>{if(!Array.isArray(s)||!s.length)return;setVehicleRoute(v=>({sightings:s,nonce:v.nonce+1}));navigate('/map')},[navigate])
 const openInvestigation=useCallback((init={})=>{setSearchInit(init);setShowSearch(true);try{sessionStorage.setItem(RETURN_ROUTE_KEY,path)}catch{}navigate('/investigations')},[navigate,path])
 const closeInvestigation=useCallback(()=>{setShowSearch(false);setSearchInit(null);let target='/feeds';try{target=sessionStorage.getItem(RETURN_ROUTE_KEY)||target;sessionStorage.removeItem(RETURN_ROUTE_KEY)}catch{}navigate(target)},[navigate])
 const openAlertPage=useCallback(()=>navigate('/alerts'),[navigate])
 const login=useCallback(async credentials=>{const r=await api.login(credentials);localStorage.setItem('sentinel.jwt',r.access_token);setPrincipal(r.user);setAuthReady(true);setAuthError('');const target=readAuthRoute();writeAuthRoute(null);navigate(target,{replace:true})},[navigate])
 const logout=useCallback(async()=>{try{await api.logout()}catch{}localStorage.removeItem('sentinel.jwt');writeSession(null);writeAuthRoute(null);setPrincipal(null);setAlerts([]);setCounts(null);setTestMode(false);setTestSession(null);navigate('/feeds',{replace:true})},[navigate])
 const onboard=useCallback(async body=>{const c=await api.onboardCamera(body);setCameras(v=>[...v,c].sort((a,b)=>(a.stream_id||0)-(b.stream_id||0)));setProductionCameras(v=>[...v,c].sort((a,b)=>(a.stream_id||0)-(b.stream_id||0)));return c},[])
 const importCameras=useCallback(async file=>{const r=await api.importCameras(file);const cams=await api.getCameras();setCameras(cams);setProductionCameras(cams);return r},[])
 const startTest=useCallback(session=>{if(!session?.id)return;writeSession(session.id);setTestSession(session);setTestMode(true);setShowTestDiagnostics(false);navigate('/test')},[navigate])
 const openTest=useCallback(async()=>{try{const s=await api.getActiveTestSession();if(s)return startTest(s)}catch(error){console.warn('test session lookup:',error)}setShowTestDiagnostics(true);navigate('/test')},[navigate,startTest])
 const exitTest=useCallback(()=>{writeSession(null);setTestMode(false);setTestSession(null);setAlerts([]);setCounts(null);setPipelineStats(null);setAnalytics([]);api.getCameras().then(r=>{setCameras(r);setProductionCameras(r)}).catch(()=>{});navigate('/feeds',{replace:true})},[navigate])
 const showMap=path==='/map',showAlerts=path==='/alerts',showFeeds=path==='/feeds'||path==='/test',showInvestigate=path==='/investigations'
 const title=showMap?'GIS Map':showInvestigate?'Investigate':showAlerts?'Alerts':path==='/test'?'Test Mode':'Monitor'
 if(authRequired===null||!authReady)return <div className="sentinel-loading-screen">Loading Sentinel…</div>
 if(authRequired&&!principal)return <LoginModal onLogin={login} error={authError}/>
 return <div className="sentinel-shell"><Navbar path={path} onNavigate={navigate} alertCount={counts?.unacknowledged||0} onWatchlistOpen={()=>setShowWatchlist(true)} onOnboardOpen={()=>setShowOnboard(true)} onVendorsOpen={()=>setShowVendors(true)} onTestOpen={testEnabled?()=>testMode?exitTest():openTest():null} testMode={testMode} principal={principal} onLogout={logout} onAlertsOpen={openAlertPage}/><main className="sentinel-main"><header className="sentinel-topbar"><div className="sentinel-topbar-title">{title}</div>{showMap?<div style={{flex:1}}/>:<CameraSearch value={headerSearch} onChange={setHeaderSearch} onViewCamera={openCamera} onLocateCamera={locateCamera}/>}<div className="sentinel-topbar-actions"><div className="sentinel-status"><span className="sentinel-live-pulse"/>LIVE</div><NotificationBell alerts={alerts} count={counts?.unacknowledged||0} onAck={ack} onOpenAll={openAlertPage} onInvestigate={a=>a?.details?.plate_text&&openInvestigation({tab:'plate',query:a.details.plate_text})}/><time className="sentinel-clock" dateTime={now.toISOString()}>{now.toLocaleTimeString('en-IN',{hour12:false})}</time></div></header><div className={`sentinel-route sentinel-route-${routeMotion%2?'b':'a'}`} style={{display:'flex',flex:1,minHeight:0,overflow:'hidden'}}>{showAlerts?<AlertsPage initialAlerts={alerts} onTransition={transitionAlert} onOpenInvestigation={openInvestigation}/>:<div style={{flex:1,minWidth:0,overflow:'hidden',position:'relative',display:'flex',flexDirection:'column'}}>{showMap?<><MapSearch cameras={productionCameras} onLocate={locateCamera}/><MapView cameras={productionCameras} alerts={alerts} focusCameraId={mapFocus.id} focusNonce={mapFocus.nonce} route={vehicleRoute.sightings} routeFocusNonce={vehicleRoute.nonce}/></>:showFeeds?<div style={{flex:1,minHeight:0}}><CameraGrid cameras={cameras} alertsByCam={alertsByCam} analyticsByCam={analyticsByCam} pipelineStats={pipelineStats} onLocate={testMode?undefined:locateCamera} focusCameraId={cameraFocus.id} focusNonce={cameraFocus.nonce}/></div>:null}</div>}</div></main>{showInvestigate&&<InvestigationPanel init={searchInit} testMode={testMode} testSession={testSession} onClose={closeInvestigation} onLocateRoute={locateRoute}/>} {showWatchlist&&<WatchlistModal onClose={()=>setShowWatchlist(false)}/>} {showOnboard&&<OnboardCameraModal onClose={()=>setShowOnboard(false)} onSaved={onboard} onImport={importCameras}/>} {showVendors&&<VendorModal onClose={()=>setShowVendors(false)}/>} {showTestDiagnostics&&<TestDiagnosticsModal onClose={()=>{setShowTestDiagnostics(false);navigate('/feeds',{replace:true})}} onStarted={startTest}/>}</div>
}
