import { useCallback, useEffect, useRef, useState, memo } from 'react'
import { createPortal } from 'react-dom'
import Hls from 'hls.js'
import { useCameraPlayerSlot } from './cameraPlayerManager'

const MAX_PLAYERS = 12

const BufferIndicator=({buffering})=>buffering?<div style={{position:'absolute',inset:0,display:'grid',placeItems:'center',zIndex:4,background:'rgba(0,0,0,.18)',color:'rgba(255,255,255,.7)',fontSize:11}}>Connecting…</div>:null


const CCTV_SOURCE_BASE=(import.meta.env.VITE_CCTV_BASE_URL||'https://cctv.corp8.cloud').replace(/\/$/,'')
const paddedId = cam => String(cam?.stream_id || cam?.id || '?').replace(/^cam/i, '').padStart(2, '0')
const streamAspect = cam => { const w=Number(cam?.effective_width ?? cam?.width), h=Number(cam?.effective_height ?? cam?.height); return w>0&&h>0?w/h:16/9 }
const playbackSources = cam => {
  const id=paddedId(cam)
  if(cam?.is_test && cam?.stream_url){
    const match=String(cam.stream_url).match(/\/api\/test\/sessions\/([^/]+)\/feeds\/([^/]+)\/video/)
    if(match) return {hls:`/test-hls/test/${match[1]}/cam${match[2]}/index.m3u8`,fallback:cam.stream_url}
  }
  const proxy=`/api/cctv/cam${id}/index.m3u8`
  const configured=String(cam?.source_hls_url||cam?.hls_url||'').split('?')[0]
  const hls=configured.startsWith('http://')||configured.startsWith('https://') ? configured : CCTV_SOURCE_BASE+`/cam${id}/index.m3u8`
  return {hls,fallback:hls===proxy?null:proxy}
}

const HLS_CONFIG={
  lowLatencyMode:true,maxBufferLength:8,maxMaxBufferLength:16,
  liveSyncDurationCount:2,liveMaxLatencyDurationCount:4,
  manifestLoadingTimeOut:10000,manifestLoadingMaxRetry:3,
  levelLoadingTimeOut:10000,fragLoadingTimeOut:20000,
  enableWorker:true,startFragPrefetch:true,testBandwidth:false,
  xhrSetup:xhr=>{xhr.withCredentials=true},
}

function LivePlayer({cam,muted=true,onLiveStatus,onAspectChange,fit='contain'}){
  const videoRef=useRef(null),hlsRef=useRef(null),fallbackRef=useRef(null),liveRef=useRef(false),sources=playbackSources(cam)
  const [mode,setMode]=useState('hls'),[snapshot,setSnapshot]=useState(null),[live,setLive]=useState(false),[buffering,setBuffering]=useState(true)
  const cleanup=useCallback(()=>{clearTimeout(fallbackRef.current);hlsRef.current?.destroy();hlsRef.current=null},[])
  const markPlaying=useCallback(()=>{clearTimeout(fallbackRef.current);liveRef.current=true;setLive(true);setBuffering(false)},[])
  const fallbackToSource=useCallback(from=>{clearTimeout(fallbackRef.current);hlsRef.current?.destroy();hlsRef.current=null;if(from==='hls'&&sources.fallback){setMode('stream');setBuffering(true)}else{setMode('snapshot');setBuffering(false);liveRef.current=false;setLive(false)}},[sources.fallback])
  useEffect(()=>{cleanup();setMode('hls');setLive(false);liveRef.current=false;setBuffering(true)},[cam.id,sources.hls,sources.fallback,cleanup])
  useEffect(()=>{let cancelled=false,objectUrl=null;const load=async()=>{if(cam.is_test)return;try{const r=await fetch('/api/cameras/'+cam.id+'/snapshot?t='+Date.now(),{credentials:'include',cache:'no-store'});if(!r.ok)return;const b=await r.blob();objectUrl=URL.createObjectURL(b);if(!cancelled)setSnapshot(objectUrl);else URL.revokeObjectURL(objectUrl)}catch{}};load();const timer=setInterval(()=>{if(!liveRef.current)load()},5000);return()=>{cancelled=true;clearInterval(timer);if(objectUrl)URL.revokeObjectURL(objectUrl)}},[cam.id,cam.is_test])
  useEffect(()=>{if(mode!=='hls'||!sources.hls)return;const v=videoRef.current;fallbackRef.current=setTimeout(()=>fallbackToSource('hls'),9000);if(Hls.isSupported()){const h=new Hls({lowLatencyMode:true,backBufferLength:8,maxBufferLength:8,maxMaxBufferLength:16,liveSyncDurationCount:2,liveMaxLatencyDurationCount:4,manifestLoadingTimeOut:7000,manifestLoadingMaxRetry:2,manifestLoadingRetryDelay:500,levelLoadingTimeOut:7000,levelLoadingMaxRetry:2,levelLoadingRetryDelay:500,fragLoadingTimeOut:12000,fragLoadingMaxRetry:2,fragLoadingRetryDelay:500,enableWorker:true,startFragPrefetch:true,testBandwidth:false,xhrSetup:(x,u)=>{try{x.withCredentials=new URL(u,window.location.href).origin===window.location.origin}catch{x.withCredentials=true}}});h.on(Hls.Events.MANIFEST_PARSED,()=>setBuffering(true));h.on(Hls.Events.ERROR,(_,d)=>{if(!d.fatal)return;if(d.type===Hls.ErrorTypes.MEDIA_ERROR){try{h.recoverMediaError();return}catch{}}if(d.type===Hls.ErrorTypes.NETWORK_ERROR){try{h.startLoad();return}catch{}}fallbackToSource('hls')});h.attachMedia(v);h.loadSource(sources.hls);hlsRef.current=h}else if(v.canPlayType('application/vnd.apple.mpegurl')){v.src=sources.hls;v.play().catch(()=>{})}else fallbackToSource('hls');return()=>{cleanup();v?.removeAttribute('src');v?.load()}},[mode,sources.hls,fallbackToSource,cleanup])
  useEffect(()=>{if(mode!=='stream'||!sources.fallback)return;const v=videoRef.current;v.preload='auto';v.src=sources.fallback;v.play().catch(()=>{});const fail=()=>fallbackToSource('stream');v.addEventListener('error',fail);v.addEventListener('playing',markPlaying);fallbackRef.current=setTimeout(fail,20000);return()=>{cleanup();v.removeEventListener('error',fail);v.removeEventListener('playing',markPlaying);v.removeAttribute('src');v.load()}},[mode,sources.fallback,fallbackToSource,cleanup,markPlaying])
  useEffect(()=>{onLiveStatus?.(live)},[live,onLiveStatus])
  const metadata=e=>{const v=e.currentTarget;if(v.videoWidth&&v.videoHeight)onAspectChange?.(v.videoWidth/v.videoHeight)}
  return <div style={{position:'absolute',inset:0,background:'#000'}}>{snapshot&&!live&&<img src={snapshot} alt="Latest camera frame" onLoad={metadata} style={{position:'absolute',inset:0,width:'100%',height:'100%',objectFit:fit}}/>}<video ref={videoRef} autoPlay muted={muted} playsInline loop={cam?.is_test} onPlaying={markPlaying} onLoadedMetadata={metadata} style={{position:'absolute',inset:0,width:'100%',height:'100%',objectFit:fit,display:(mode==='hls'||mode==='stream')?'block':'none'}}/>{!live&&(mode==='hls'||mode==='stream')&&!snapshot&&<BufferIndicator buffering={buffering}/>}</div>
}const CameraCard=memo(function CameraCard({cam,alertCount=0,onFocus,onLocate,testMode=false,onRemoveTestFeed}){
  const stageRef=useRef(null),active=useCameraPlayerSlot(cam.id,stageRef),[live,setLive]=useState(false),[aspect,setAspect]=useState(()=>streamAspect(cam))
  const health=String(cam.health_status||cam.status||'unknown').toUpperCase()
  return <article ref={stageRef} onClick={()=>onFocus?.(cam)} style={{background:'var(--surface2)',border:`1px solid ${alertCount?'var(--high)':'var(--border)'}`,borderRadius:8,overflow:'hidden',cursor:'pointer'}}>
    <div style={{position:'relative',aspectRatio:aspect,background:'#000'}}>
      {active&&<LivePlayer cam={cam} onLiveStatus={setLive} onAspectChange={setAspect}/>}
      <div style={{position:'absolute',top:0,left:0,right:0,zIndex:6,padding:'7px 9px',display:'flex',gap:7,background:'linear-gradient(rgba(0,0,0,.72),transparent)',color:'#fff',fontSize:10,fontWeight:800}}><span>CAM-{paddedId(cam)}</span><span style={{marginLeft:'auto'}}>{live?'LIVE':health}</span></div>
      {alertCount>0&&<span style={{position:'absolute',top:7,left:60,zIndex:7,background:'var(--high)',color:'#fff',borderRadius:4,padding:'2px 6px',fontSize:9,fontWeight:800}}>{alertCount}</span>}
      <div style={{position:'absolute',left:7,bottom:7,zIndex:8}}>{testMode&&<button type="button" onClick={e=>{e.stopPropagation();onRemoveTestFeed?.(cam)}} title="Remove test feed" aria-label="Remove test feed" style={{border:'1px solid rgba(255,120,120,.55)',background:'rgba(75,0,0,.78)',color:'#fff',borderRadius:4,padding:'4px 7px',cursor:'pointer'}}>Remove</button>}</div><div style={{position:'absolute',right:7,bottom:7,zIndex:7,display:'flex',gap:5}}><button onClick={e=>{e.stopPropagation();onFocus?.(cam)}} title="View live feed" aria-label="View live feed" style={{border:'1px solid rgba(255,255,255,.4)',background:'rgba(0,0,0,.72)',color:'#fff',borderRadius:4,padding:'4px 7px',cursor:'pointer'}}>View</button>{onLocate&&<button onClick={e=>{e.stopPropagation();onLocate(cam)}} title="Locate on map" aria-label="Locate on map" style={{border:'1px solid rgba(255,255,255,.4)',background:'rgba(0,0,0,.72)',color:'#fff',borderRadius:4,padding:'4px 7px',cursor:'pointer'}}>Map</button>}</div>
    </div>
    <div style={{padding:'8px 10px',fontSize:11}}><b style={{display:'block',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{cam.name||`CAM-${paddedId(cam)}`}</b><span style={{display:'block',marginTop:3,color:'var(--text2)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{cam.location||'Location not registered'}</span></div>
  </article>
})

export default function CameraGrid({cameras=[],alertsByCam={},onLocate,focusCameraId,focusNonce=0,pipelineStats,testMode=false,onManageTestFeeds,onRemoveTestFeed}){
  const [cols,setCols]=useState(()=>{const n=Number(localStorage.getItem('sentinel.camera-grid.columns.v1'));return [2,3,4,5].includes(n)?n:3}),[focused,setFocused]=useState(null)
  useEffect(()=>{if(!focusCameraId)return;const cam=cameras.find(c=>String(c.id)===String(focusCameraId));if(cam)setFocused(cam)},[focusCameraId,focusNonce,cameras])
  const open=cam=>setFocused(cam)
  return <div style={{display:'flex',flexDirection:'column',width:'100%',maxWidth:'100%',minWidth:0,height:'100%',background:'var(--bg)',overflow:'hidden',boxSizing:'border-box'}}>
    <header style={{display:'flex',alignItems:'center',gap:10,padding:'8px 12px',borderBottom:'1px solid var(--border)',background:'var(--surface)'}}><b className="camera-grid-primary-metric">{cameras.length} Cameras</b>{pipelineStats&&<span className="camera-grid-secondary-metrics"><span className="camera-grid-metric-value">Frames {Number(pipelineStats.raw_frames||0).toLocaleString()}</span><span aria-hidden="true">·</span><span className="camera-grid-metric-value">Detections {Number(pipelineStats.detections||0).toLocaleString()}</span></span>}<div style={{marginLeft:'auto',display:'flex',gap:3}}>{[2,3,4,5].map(n=><button key={n} onClick={()=>{setCols(n);localStorage.setItem('sentinel.camera-grid.columns.v1',String(n))}} aria-label={`${n} camera columns`} style={{width:28,height:26,borderRadius:5,border:`1px solid ${cols===n?'var(--accent)':'var(--border)'}`,background:cols===n?'var(--accent)':'var(--surface2)',color:cols===n?'var(--on-accent)':'var(--text)',cursor:'pointer'}}>{n}</button>)}</div></header>
    <main style={{flex:1,minWidth:0,minHeight:0,width:'100%',maxWidth:'100%',overflowY:'auto',overflowX:'hidden',padding:10,boxSizing:'border-box'}}><div style={{display:'grid',width:'100%',minWidth:0,maxWidth:'100%',gridTemplateColumns:`repeat(${cols},minmax(0,1fr))`,gap:8,boxSizing:'border-box'}}>{cameras.map(cam=><CameraCard key={cam.id} cam={cam} alertCount={alertsByCam[cam.id]||0} onFocus={open} onLocate={onLocate} testMode={testMode} onRemoveTestFeed={onRemoveTestFeed}/>)}</div>{testMode&&<button type="button" onClick={onManageTestFeeds} className="test-feed-add-button" aria-label="Add test feed video" title="Add test feed video">+</button>}</main>
    {focused&&typeof document!=='undefined'&&createPortal(
      <div onClick={e=>e.target===e.currentTarget&&setFocused(null)} className="camera-fullscreen-overlay">
        <section className="camera-fullscreen-panel" aria-label={`Camera CAM-${paddedId(focused)} fullscreen view`}>
          <header className="camera-fullscreen-header">
            <div className="camera-fullscreen-title">
              <b>CAM-{paddedId(focused)}</b>
              <span>{focused.name||'Camera'}</span>
            </div>
            <button type="button" onClick={()=>setFocused(null)} className="camera-fullscreen-close">Close</button>
          </header>
          <div className="camera-fullscreen-stage" style={{aspectRatio:streamAspect(focused)}}>
            <LivePlayer cam={focused} muted={false} active managed={false} fit="contain"/>
          </div>
        </section>
      </div>,
      document.body
    )}
  </div>
}
