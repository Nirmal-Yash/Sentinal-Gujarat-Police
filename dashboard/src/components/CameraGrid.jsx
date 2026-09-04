import { useCallback, useEffect, useRef, useState, memo } from 'react'
import Hls from 'hls.js'
import { useCameraPlayerSlot } from './cameraPlayerManager'

const MAX_PLAYERS = 12

const paddedId = cam => String(cam?.stream_id || cam?.id || '?').replace(/^cam/i, '').padStart(2, '0')
const streamAspect = cam => { const w=Number(cam?.effective_width ?? cam?.width), h=Number(cam?.effective_height ?? cam?.height); return w>0&&h>0?w/h:16/9 }
const playbackSources = cam => {
  const id=paddedId(cam)
  if(cam?.is_test && cam?.stream_url){
    const match=String(cam.stream_url).match(/\/api\/test\/sessions\/([^/]+)\/feeds\/([^/]+)\/video/)
    if(match) return {hls:`/test-hls/test/${match[1]}/cam${match[2]}/index.m3u8`}
  }
  const configured=String(cam?.hls_url||'').split('?')[0]
  const hls=configured && (configured.startsWith('https://cctv.corp8.cloud/')||configured.startsWith('/test-hls/')) ? configured : `https://cctv.corp8.cloud/cam${id}/index.m3u8`
  return {hls}
}

function captureFrozenFrame(video){
  if(!video || !video.videoWidth || !video.videoHeight) return null
  try{
    const canvas=captureFrozenFrame.canvas || (captureFrozenFrame.canvas=document.createElement('canvas'))
    canvas.width=video.videoWidth; canvas.height=video.videoHeight
    const ctx=canvas.getContext('2d',{willReadFrequently:false}); if(!ctx)return null
    ctx.drawImage(video,0,0,canvas.width,canvas.height)
    return canvas.toDataURL('image/jpeg',0.82)
  }catch{return null}
}

function LivePlayer({cam,muted=true,managed=false,active=true,onLiveStatus,onAspectChange,fit='contain'}){
  const videoRef=useRef(null),hlsRef=useRef(null),retryRef=useRef(null),snapshotRef=useRef(null),wasLiveRef=useRef(false)
  const [state,setState]=useState(managed?'IDLE':'LOADING'),[snapshot,setSnapshot]=useState(null),[live,setLive]=useState(false)
  const sources=playbackSources(cam)
  const replaceSnapshot=useCallback(url=>{setSnapshot(prev=>{if(prev && prev!==url && prev.startsWith('blob:'))URL.revokeObjectURL(prev);snapshotRef.current=url;return url})},[])
  const cleanup=useCallback(()=>{clearTimeout(retryRef.current);hlsRef.current?.destroy();hlsRef.current=null},[])
  const loadSnapshot=useCallback(async()=>{try{const r=await fetch(`/api/cameras/${cam.id}/snapshot?t=${Date.now()}`,{credentials:'include',cache:'no-store'});if(r.ok)replaceSnapshot(URL.createObjectURL(await r.blob()))}catch{}},[cam.id,replaceSnapshot])
  const start=useCallback(()=>{
    cleanup(); const video=videoRef.current; if(!video || !sources.hls)return
    setState('LOADING'); setLive(false)
    const fail=()=>{
      cleanup(); setLive(false);
      if(cam?.is_test && cam?.stream_url){
        setState('FALLBACK');
        video.src=cam.stream_url;
        video.load();
        const fallbackTimer=setTimeout(()=>{if(!wasLiveRef.current){setState('ERROR')}},8000);
        video.onplaying=()=>{clearTimeout(fallbackTimer);wasLiveRef.current=true;setLive(true);setState('ACTIVE')};
        return;
      }
      setState('ERROR');
      clearTimeout(retryRef.current);
      retryRef.current=setTimeout(()=>start(),30000);
    }
    if(Hls.isSupported()){
      const hls=new Hls({enableWorker:true,lowLatencyMode:true,backBufferLength:6,maxBufferLength:12,maxMaxBufferLength:24,liveSyncDurationCount:3,liveMaxLatencyDurationCount:6,maxBufferHole:.5,fragLoadingMaxRetry:3,fragLoadingRetryDelay:700,manifestLoadingMaxRetry:3,manifestLoadingRetryDelay:700,xhrSetup:(xhr)=>{xhr.withCredentials=true}})
      hls.attachMedia(video);hls.loadSource(sources.hls)
      hls.on(Hls.Events.ERROR,(_,d)=>{if(!d.fatal)return;if(d.type===Hls.ErrorTypes.MEDIA_ERROR){try{hls.recoverMediaError();return}catch{}}if(d.type===Hls.ErrorTypes.NETWORK_ERROR){try{hls.startLoad();return}catch{}}fail()})
      hlsRef.current=hls
    }else if(video.canPlayType('application/vnd.apple.mpegurl')){video.src=sources.hls}else{fail();return}
    clearTimeout(retryRef.current);retryRef.current=setTimeout(()=>{if(!wasLiveRef.current)fail()},14000)
  },[cleanup,sources.hls])
  useEffect(()=>{
    if(managed && !active){const frozen=captureFrozenFrame(videoRef.current);if(frozen)replaceSnapshot(frozen);cleanup();setLive(false);setState(wasLiveRef.current?'SUSPENDED':'IDLE');return ()=>cleanup()}
    start(); return ()=>cleanup()
  },[managed,active,start,cleanup,replaceSnapshot])
  useEffect(()=>{loadSnapshot();const t=setInterval(()=>{if(!live)loadSnapshot()},15000);return()=>clearInterval(t)},[loadSnapshot,live])
  useEffect(()=>{onLiveStatus?.(live)},[live,onLiveStatus])
  const markPlaying=()=>{wasLiveRef.current=true;setLive(true);setState('ACTIVE')}
  const metadata=e=>{const v=e.currentTarget;if(v.videoWidth&&v.videoHeight)onAspectChange?.(v.videoWidth/v.videoHeight)}
  const visibleImage=!live && snapshot
  return <div style={{position:'absolute',inset:0,background:'#000'}}>
    {visibleImage&&<img src={snapshot} alt="Latest camera frame" onLoad={metadata} style={{position:'absolute',inset:0,width:'100%',height:'100%',objectFit:fit,zIndex:1}}/>}
    <video ref={videoRef} autoPlay muted={muted} playsInline loop={cam?.is_test} onPlaying={markPlaying} onLoadedMetadata={metadata} style={{position:'absolute',inset:0,width:'100%',height:'100%',objectFit:fit,display:state==='ACTIVE'||state==='LOADING'?'block':'none',zIndex:2}}/>
    {state==='ERROR'&&<div style={{position:'absolute',inset:0,zIndex:3,display:'grid',placeItems:'center',background:'rgba(0,0,0,.28)',color:'rgba(255,255,255,.75)',fontSize:11}}>{cam?.is_test?'Test video unavailable':'Camera unavailable'}</div>}
    {state==='LOADING'&&!snapshot&&<div style={{position:'absolute',inset:0,zIndex:3,display:'grid',placeItems:'center',color:'rgba(255,255,255,.65)',fontSize:11}}>Connecting…</div>}
    {live&&<span style={{position:'absolute',right:8,bottom:6,zIndex:5,color:'#fff',fontSize:9,fontWeight:800,letterSpacing:.5}}>● LIVE</span>}
  </div>
}

const CameraCard=memo(function CameraCard({cam,alertCount=0,onFocus,onLocate}){
  const stageRef=useRef(null),active=useCameraPlayerSlot(cam.id,stageRef),[live,setLive]=useState(false),[aspect,setAspect]=useState(()=>streamAspect(cam))
  const health=String(cam.health_status||cam.status||'unknown').toUpperCase()
  return <article ref={stageRef} onClick={()=>onFocus?.(cam)} style={{background:'var(--surface2)',border:`1px solid ${alertCount?'var(--high)':'var(--border)'}`,borderRadius:8,overflow:'hidden',cursor:'pointer'}}>
    <div style={{position:'relative',aspectRatio:aspect,background:'#000'}}>
      <LivePlayer cam={cam} managed active={active} onLiveStatus={setLive} onAspectChange={setAspect}/>
      <div style={{position:'absolute',top:0,left:0,right:0,zIndex:6,padding:'7px 9px',display:'flex',gap:7,background:'linear-gradient(rgba(0,0,0,.72),transparent)',color:'#fff',fontSize:10,fontWeight:800}}><span>CAM-{paddedId(cam)}</span><span style={{marginLeft:'auto'}}>{live?'LIVE':health}</span></div>
      {alertCount>0&&<span style={{position:'absolute',top:7,left:60,zIndex:7,background:'var(--high)',color:'#fff',borderRadius:4,padding:'2px 6px',fontSize:9,fontWeight:800}}>{alertCount}</span>}
      <div style={{position:'absolute',right:7,bottom:7,zIndex:7,display:'flex',gap:5}}><button onClick={e=>{e.stopPropagation();onFocus?.(cam)}} title="View live feed" aria-label="View live feed" style={{border:'1px solid rgba(255,255,255,.4)',background:'rgba(0,0,0,.72)',color:'#fff',borderRadius:4,padding:'4px 7px',cursor:'pointer'}}>View</button>{onLocate&&<button onClick={e=>{e.stopPropagation();onLocate(cam)}} title="Locate on map" aria-label="Locate on map" style={{border:'1px solid rgba(255,255,255,.4)',background:'rgba(0,0,0,.72)',color:'#fff',borderRadius:4,padding:'4px 7px',cursor:'pointer'}}>Map</button>}</div>
    </div>
    <div style={{padding:'8px 10px',fontSize:11}}><b style={{display:'block',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{cam.name||`CAM-${paddedId(cam)}`}</b><span style={{display:'block',marginTop:3,color:'var(--text2)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{cam.location||'Location not registered'}</span></div>
  </article>
})

export default function CameraGrid({cameras=[],alertsByCam={},onLocate,focusCameraId,focusNonce=0,pipelineStats}){
  const [cols,setCols]=useState(()=>{const n=Number(localStorage.getItem('sentinel.camera-grid.columns.v1'));return [2,3,4,5].includes(n)?n:3}),[focused,setFocused]=useState(null)
  useEffect(()=>{if(!focusCameraId)return;const cam=cameras.find(c=>String(c.id)===String(focusCameraId));if(cam)setFocused(cam)},[focusCameraId,focusNonce,cameras])
  const open=cam=>setFocused(cam)
  return <div style={{display:'flex',flexDirection:'column',width:'100%',maxWidth:'100%',minWidth:0,height:'100%',background:'var(--bg)',overflow:'hidden',boxSizing:'border-box'}}>
    <header style={{display:'flex',alignItems:'center',gap:10,padding:'8px 12px',borderBottom:'1px solid var(--border)',background:'var(--surface)'}}><b className="camera-grid-primary-metric">{cameras.length} Cameras</b>{pipelineStats&&<span className="camera-grid-secondary-metrics"><span className="camera-grid-metric-value">Frames {Number(pipelineStats.raw_frames||0).toLocaleString()}</span><span aria-hidden="true">·</span><span className="camera-grid-metric-value">Detections {Number(pipelineStats.detections||0).toLocaleString()}</span></span>}<div style={{marginLeft:'auto',display:'flex',gap:3}}>{[2,3,4,5].map(n=><button key={n} onClick={()=>{setCols(n);localStorage.setItem('sentinel.camera-grid.columns.v1',String(n))}} aria-label={`${n} camera columns`} style={{width:28,height:26,borderRadius:5,border:`1px solid ${cols===n?'var(--accent)':'var(--border)'}`,background:cols===n?'var(--accent)':'var(--surface2)',color:cols===n?'var(--on-accent)':'var(--text)',cursor:'pointer'}}>{n}</button>)}</div></header>
    <main style={{flex:1,minWidth:0,minHeight:0,width:'100%',maxWidth:'100%',overflowY:'auto',overflowX:'hidden',padding:10,boxSizing:'border-box'}}><div style={{display:'grid',width:'100%',minWidth:0,maxWidth:'100%',gridTemplateColumns:`repeat(${cols},minmax(0,1fr))`,gap:8,boxSizing:'border-box'}}>{cameras.map(cam=><CameraCard key={cam.id} cam={cam} alertCount={alertsByCam[cam.id]||0} onFocus={open} onLocate={onLocate}/>)}</div></main>
    {focused&&<div onClick={e=>e.target===e.currentTarget&&setFocused(null)} className="camera-fullscreen-overlay"><section className="camera-fullscreen-panel"><header className="camera-fullscreen-header"><div className="camera-fullscreen-title"><b>CAM-{paddedId(focused)}</b><span>{focused.name||'Camera'}</span></div><button type="button" onClick={()=>setFocused(null)} className="camera-fullscreen-close">Close</button></header><div className="camera-fullscreen-stage" style={{aspectRatio:streamAspect(focused)}}><LivePlayer cam={focused} muted={false} active managed={false} fit="contain"/></div></section></div>}
  </div>
}
