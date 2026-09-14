import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { isValidIndianPlate, plateValidationMessage } from '../lib/validators'
import { sortSightingsChronologically } from '../lib/routeSightings'
import { Input } from './ui/input'
import { Button } from './ui/button'

const CloseIcon=()=><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="m18 6-12 12M6 6l12 12"/></svg>
const UserIcon=()=><svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><circle cx="12" cy="8" r="3"/><path d="M5 20a7 7 0 0 1 14 0"/></svg>
const RouteIcon=()=><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="6" cy="19" r="3"/><path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15"/><circle cx="18" cy="5" r="3"/></svg>
const ImageIcon=()=><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg>

// EvidenceThumbnail: lazy-loads detection frame via IntersectionObserver, shows lightbox on click
function BboxOverlay({ bbox, frameWidth, frameHeight }) {
  const x1=Number(bbox?.x1??bbox?.[0]),y1=Number(bbox?.y1??bbox?.[1]),x2=Number(bbox?.x2??bbox?.[2]),y2=Number(bbox?.y2??bbox?.[3])
  const w=Number(frameWidth)||1920,h=Number(frameHeight)||1080
  if(!Number.isFinite(x1+y1+x2+y2)||x2<=x1||y2<=y1)return null
  return <div style={{position:'absolute',left:`${Math.max(0,Math.min(100,x1/w*100))}%`,top:`${Math.max(0,Math.min(100,y1/h*100))}%`,width:`${Math.max(1,Math.min(100,(x2-x1)/w*100))}%`,height:`${Math.max(1,Math.min(100,(y2-y1)/h*100))}%`,border:'2px solid var(--accent)',boxSizing:'border-box',pointerEvents:'none'}}/>
}

function EvidenceThumbnail({ evidence, plate, cameraName, capturedAt, bbox }) {
  const [visible, setVisible] = useState(false)
  const [imgState, setImgState] = useState('idle')
  const [lightbox, setLightbox] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!evidence?.available) return
    const el = ref.current; if (!el) return
    const obs = new IntersectionObserver(([entry]) => { if (entry.isIntersecting) { setVisible(true); obs.disconnect() } }, { rootMargin: '120px' })
    obs.observe(el); return () => obs.disconnect()
  }, [evidence?.available])

  useEffect(() => { if (visible && imgState === 'idle') setImgState('loading') }, [visible, imgState])

  if (!evidence?.available) return null
  const thumbUrl = evidence.thumbnail_url || evidence.frame_url
  const fullUrl = evidence.frame_url

  return (
    <>
      <div ref={ref} onClick={() => imgState === 'loaded' && setLightbox(true)}
           style={{ width:120,minWidth:120,height:80,borderRadius:7,overflow:'hidden',border:'1px solid var(--border)',
                    background:'var(--surface3)',cursor:imgState==='loaded'?'zoom-in':'default',position:'relative',flexShrink:0 }}>
        {imgState !== 'loaded' && (
          <div style={{ position:'absolute',inset:0,background:'var(--surface3)',display:'flex',alignItems:'center',justifyContent:'center' }}>
            {imgState === 'loading' ? <Shimmer /> : <ImageIcon />}
          </div>
        )}
        {visible && <img src={thumbUrl} alt="Detection" onLoad={()=>setImgState('loaded')} onError={()=>setImgState('error')}
                         style={{ width:'100%',height:'100%',objectFit:'cover',display:imgState==='loaded'?'block':'none' }} />}
        {imgState === 'loaded' && <div style={{ position:'absolute',bottom:3,right:4,background:'rgba(0,0,0,.65)',borderRadius:3,padding:'1px 4px',fontSize:8,color:'#fff' }}>View</div>}
      </div>
      {lightbox && (
        <div onClick={()=>setLightbox(false)} style={{ position:'fixed',inset:0,background:'rgba(0,0,0,.82)',display:'flex',alignItems:'center',justifyContent:'center',zIndex:9999,padding:24 }}>
          <div onClick={e=>e.stopPropagation()} style={{ background:'var(--surface)',borderRadius:12,overflow:'hidden',maxWidth:'90vw',maxHeight:'90vh',display:'flex',flexDirection:'column',border:'1px solid var(--border)',boxShadow:'var(--shadow)' }}>
            <div style={{ display:'flex',justifyContent:'space-between',alignItems:'center',padding:'10px 14px',borderBottom:'1px solid var(--border)' }}>
              <span style={{ fontWeight:850,fontSize:13 }}>{plate} — Evidence Frame</span>
              <button onClick={()=>setLightbox(false)} style={{ width:28,height:28,border:'1px solid var(--border)',borderRadius:6,background:'var(--surface2)',cursor:'pointer',display:'grid',placeItems:'center' }}><CloseIcon /></button>
            </div>
            <div style={{ overflow:'auto',padding:10,textAlign:'center' }}>
              <div style={{ position:'relative',display:'inline-block',maxWidth:'100%' }}>
                <img src={fullUrl} alt="Full frame" style={{ maxWidth:'100%',maxHeight:'70vh',borderRadius:6,objectFit:'contain',display:'block' }} />
                <BboxOverlay bbox={bbox} frameWidth={evidence?.frame_width} frameHeight={evidence?.frame_height} />
              </div>
            </div>
            <div style={{ padding:'8px 14px',borderTop:'1px solid var(--border)',fontSize:9,color:'var(--text2)',display:'flex',gap:12,flexWrap:'wrap' }}>
              <span><b>Camera:</b> {cameraName||'—'}</span>
              <span><b>Captured:</b> {capturedAt||'—'}</span>
              {evidence.sha256&&<span style={{ fontFamily:'monospace' }}>SHA256 {evidence.sha256.slice(0,16)}…</span>}
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function Shimmer() {
  return <div style={{ width:'100%',height:'100%',background:'linear-gradient(90deg,var(--surface3) 25%,var(--surface2) 50%,var(--surface3) 75%)',backgroundSize:'200% 100%',animation:'sentinel-shimmer 1.4s infinite linear' }} />
}

function ScoreBadge({ label, value, color }) {
  if (value == null) return null
  const pct = typeof value === 'number' ? value : parseFloat(value)
  if (Number.isNaN(pct)) return null
  const display = pct > 1 ? `${pct.toFixed(0)}%` : `${(pct*100).toFixed(0)}%`
  const tone = color || (pct >= (pct>1?0.75:0.75) ? 'var(--green)' : pct >= 0.5 ? 'var(--medium)' : 'var(--high)')
  return <span style={{ display:'inline-flex',alignItems:'center',gap:3,padding:'2px 6px',borderRadius:5,fontSize:9,fontWeight:750,background:`color-mix(in srgb,${tone} 14%,transparent)`,border:`1px solid color-mix(in srgb,${tone} 35%,transparent)`,color:tone,whiteSpace:'nowrap' }}>{label}: {display}</span>
}

function SightingCard({ d, journeyLoading, onShowJourney }) {
  const timestamp = fmt(d.event_at||d.timestamp)
  const camName = d.cam_name||d.camera_label||`Stream ${d.stream_id||'—'}`
  return (
    <article style={{ display:'flex',alignItems:'flex-start',gap:10,padding:'11px 12px',marginBottom:7,borderRadius:9,background:'var(--surface2)',border:'1px solid var(--border)' }}>
      <EvidenceThumbnail evidence={d.evidence} plate={d.plate_text||'Sighting'} cameraName={camName} capturedAt={timestamp} bbox={d.bbox} />
      <div style={{ flex:1,minWidth:0 }}>
        <b style={{ fontSize:13 }}>{d.plate_text||'Plate sighting'}</b>
        <div style={{ fontSize:10,color:'var(--text2)',marginTop:2 }}>{camName} · {timestamp}</div>
        <div style={{ display:'flex',flexWrap:'wrap',gap:4,marginTop:5 }}>
          {d.confidence!=null && <ScoreBadge label="Detector" value={d.confidence} />}
          {d.anpr_consensus && <ScoreBadge label="Consensus" value={d.anpr_consensus} color="var(--accent-strong)" />}
          {d.ocr_confidence!=null && <ScoreBadge label="OCR" value={d.ocr_confidence} />}
          {d.raw_ocr && !d.ocr_confidence && <span style={{ fontSize:9,color:'var(--text2)',padding:'2px 5px',border:'1px solid var(--border)',borderRadius:4 }}>OCR: {d.raw_ocr}</span>}
        </div>
      </div>
      {(d.global_vehicle_id||d.track_id) && (
        <Button variant="outline" onClick={()=>onShowJourney(d)} disabled={journeyLoading===d.id}
                style={{ fontSize:10,height:30,padding:'0 10px',whiteSpace:'nowrap',flexShrink:0 }}>
          {journeyLoading===d.id?'Opening…':'Journey'}
        </Button>
      )}
    </article>
  )
}

export default function InvestigationPanel({ onClose, onLocateRoute, init, testMode=false, testSession=null, embedded=false }) {
  const [tab, setTab] = useState(init?.tab==='person'?'person':'plate')
  const [query, setQuery] = useState(init?.query||'')
  const [submitted, setSubmitted] = useState(init?.query||'')
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [journeyLoading, setJourneyLoading] = useState(null)
  const [journeyRouteLoading, setJourneyRouteLoading] = useState(false)
  const [personFiles, setPersonFiles] = useState([])
  const [personValidation, setPersonValidation] = useState({})
  const [personChecking, setPersonChecking] = useState(false)
  const [personSearching, setPersonSearching] = useState(false)
  const [personResults, setPersonResults] = useState(null)
  const [previewUrls, setPreviewUrls] = useState([])

  useEffect(()=>{ if(init?.tab) setTab(init.tab); if(init?.query){setQuery(init.query);setSubmitted(init.query)} },[init])
  useEffect(()=>{ const urls=personFiles.map(f=>URL.createObjectURL(f)); setPreviewUrls(urls); return()=>urls.forEach(URL.revokeObjectURL) },[personFiles])
  useEffect(()=>{
    let cancelled=false; if(!personFiles.length){setPersonValidation({});setPersonChecking(false);setPersonResults(null);return}
    setPersonChecking(true);setPersonResults(null)
    Promise.all(personFiles.map(async(file,i)=>{
      try{return[i,await api.validatePersonPhoto(file,testMode&&testSession?.id?testSession.id:undefined)]}
      catch(err){return[i,{valid:false,message:err.message||'Validation failed',face_count:0}]}
    })).then(entries=>{if(!cancelled){setPersonValidation(Object.fromEntries(entries));setPersonChecking(false)}})
    return()=>{cancelled=true}
  },[personFiles])

  // Auto-poll every 3s while plate investigation is active
  useEffect(()=>{
    if(tab!=='plate'||!submitted||submitted.length<3) return
    let active=true
    const poll=async()=>{ try{const r=await api.searchPlate(submitted,testMode&&testSession?{testSessionId:testSession.id}:{}); if(active) setResults(r)}catch{} }
    const timer=setInterval(poll,3000); return()=>{active=false;clearInterval(timer)}
  },[tab,submitted,testMode,testSession?.id])

  const plateError=plateValidationMessage(query.trim())
  const executePlate=async()=>{
    const value=query.trim()
    const validation=plateValidationMessage(value)
    if(validation){setError(validation);return}
    setSubmitted(value);setLoading(true);setError('')
    try{const r=await api.searchPlate(value,testMode&&testSession?{testSessionId:testSession.id}:{}); setResults(r)}
    catch(err){setResults(null);setError(err.message||'Investigation failed')}
    finally{setLoading(false)}
  }

  const showJourney=async row=>{
    const track=row.global_vehicle_id||row.track_id; if(!track) return
    setJourneyLoading(row.id)
    try{
      let sightings=[]
      if(testMode&&testSession&&row.plate_text){const r=await api.getTestPlateJourney(testSession.id,row.plate_text); sightings=(r.sightings||[]).filter(s=>s.lat!=null&&s.lng!=null)}
      else if(testMode&&testSession){const r=await api.getTestResults(testSession.id,{limit:500}); sightings=(r.detections||[]).filter(d=>String(d.track_id||'')===String(row.track_id||track)).sort((a,b)=>new Date(a.event_at||a.timestamp)-new Date(b.event_at||b.timestamp)).map(d=>({...d,lat:d.lat,lng:d.lng}))}
      else{const r=await api.searchTrack(track); sightings=r.sightings||[]}
      onLocateRoute?.(sortSightingsChronologically(sightings))
    }catch(err){setError(err.message||'Journey lookup failed')}
    finally{setJourneyLoading(null)}
  }

  const showFullJourneyRoute=async()=>{
    const plate=submitted||query
    if(!plate||!isValidIndianPlate(plate)) return
    setJourneyRouteLoading(true);setError('')
    try{
      let sightings=[]
      if(testMode&&testSession){
        const r=await api.getTestPlateJourney(testSession.id,plate)
        sightings=(r.sightings||[]).filter(s=>s.lat!=null&&s.lng!=null)
      }else{
        const r=await api.searchPlateJourney(plate)
        sightings=(r.journeys||[]).flatMap(j=>j.sightings||[]).concat(results?.detections||[]).filter(s=>s.lat!=null&&s.lng!=null)
      }
      if(!sightings.length){setError('No GPS-located sightings found for this plate.');return}
      onLocateRoute?.(sortSightingsChronologically(sightings))
    }catch(err){setError(err.message||'Journey route lookup failed')}
    finally{setJourneyRouteLoading(false)}
  }

  const addPhotos=e=>{
    const files=Array.from(e.target.files||[]).filter(f=>f.type.startsWith('image/'))
    setPersonFiles(c=>[...c,...files].slice(0,10));setPersonResults(null);setError('');e.target.value=''
  }
  const runPersonInvestigation=async()=>{
    const validFiles=personFiles.filter((_,i)=>personValidation[i]?.valid)
    if(!validFiles.length){setError('At least one image with a detected face is required.');return}
    setPersonSearching(true);setError('')
    try{
      const r=await api.investigatePerson(validFiles,testMode&&testSession?{testSessionId:testSession.id}:{})
      setPersonResults(r); setSubmitted(r.status==='matches'?`${r.matches.length} match${r.matches.length===1?'':'es'}`:'No matches')
    }catch(err){setPersonResults(null);setError(err.message||'Person investigation failed')}
    finally{setPersonSearching(false)}
  }

  const validCount=Object.values(personValidation).filter(v=>v?.valid).length
  const geoDetections=(results?.detections||[]).filter(d=>d.lat!=null&&d.lng!=null)
  const hasJourneyData=results&&(results.journeys?.length>0||geoDetections.length>=2)
  const SearchIcon=()=><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
  const containerStyle=embedded?{width:'100%',height:'100%',display:'flex',justifyContent:'center',padding:14,overflow:'hidden'}:overlay
  const sectionStyle=embedded?{...modal,width:'100%',maxWidth:1080,height:'100%',maxHeight:'100%',borderRadius:12}:modal

  return (
    <div style={containerStyle} onClick={e=>(!embedded&&e.target===e.currentTarget)&&onClose()}>
      <section style={sectionStyle} role="dialog" aria-modal={!embedded} aria-label="Investigation">
        <header style={head}>
          <div><b style={{ fontSize:17 }}>Investigate</b><div style={sub}>{tab==='plate'?'Search confirmed plate sightings and journeys.':'Upload person reference photos to find face matches.'}</div></div>
          <button onClick={onClose} aria-label="Close" style={close}><CloseIcon /></button>
        </header>
        <div style={{ padding:'12px 19px',borderBottom:'1px solid var(--border)',background:'var(--surface2)',display:'flex',alignItems:'center',justifyContent:'space-between',flexWrap:'wrap',gap:10 }}>
          <div role="tablist" style={{ display:'inline-flex',alignItems:'center',gap:4,padding:4,background:'var(--surface3)',borderRadius:10,border:'1px solid var(--border)' }}>
            {['plate','person'].map(t=>(
              <button key={t} type="button" role="tab" aria-selected={tab===t}
                      onClick={()=>{setTab(t);setQuery('');setResults(null);setError('');setSubmitted('');setPersonResults(null)}}
                      style={{ display:'inline-flex',alignItems:'center',gap:7,padding:'7px 16px',borderRadius:7,border:0,background:tab===t?'var(--accent)':'transparent',color:tab===t?'var(--on-accent)':'var(--text2)',fontSize:12,fontWeight:850,cursor:'pointer',boxShadow:tab===t?'0 2px 8px rgba(0,0,0,.18)':'none',transition:'all .18s ease' }}>
                {t==='plate'
                  ? <><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="6" width="18" height="12" rx="2"/><path d="M7 10h1M11 10h6M7 14h10"/></svg><span>Plate &amp; Vehicle</span></>
                  : <><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="8" r="4"/><path d="M6 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2"/></svg><span>Person &amp; Face</span></>}
              </button>
            ))}
          </div>
          <span style={{ fontSize:11,color:'var(--muted)',fontWeight:600 }}>{tab==='plate'?'Automatic ANPR & Journey tracking':'Face matching with ArcFace / InsightFace'}</span>
        </div>

        {tab==='plate' ? (
          <>
            <div style={toolbar}>
              <Input autoFocus value={query} onChange={e=>setQuery(e.target.value)}
                     onKeyDown={e=>e.key==='Enter'&&!loading&&query.trim().length>=3&&executePlate()}
                     placeholder="Enter number plate, e.g. GJ03AA1234" aria-label="Number plate" style={{ height:40,flex:1 }} />
              <Button onClick={executePlate} disabled={loading||Boolean(plateError)}
                      style={{ height:40,padding:'0 18px',fontSize:12,fontWeight:800,display:'inline-flex',alignItems:'center',gap:6 }}>
                <SearchIcon />{loading?'Investigating…':'Investigate'}
              </Button>
            </div>
            <div style={helper}>{submitted?`Submitted: ${submitted}`:'Submit a plate to begin investigation.'}</div>
            {hasJourneyData && (
              <div style={{ padding:'0 19px 10px',display:'flex',justifyContent:'flex-end' }}>
                <Button variant="outline" onClick={showFullJourneyRoute} disabled={journeyRouteLoading}
                        style={{ display:'flex',alignItems:'center',gap:5,fontSize:11 }}>
                  <RouteIcon />{journeyRouteLoading?'Loading route…':'Show Full Route on Map'}
                </Button>
              </div>
            )}
            <main style={body}>
              {error && <div style={errorBox}>{error}</div>}
              {results?.watchlist_hits?.length>0 && (
                <div style={watchlistBox}>
                  <b>⚠ Watchlist match</b>
                  {results.watchlist_hits.map(h=><div key={h.id} style={{ marginTop:4 }}>{h.name} — {h.description}</div>)}
                </div>
              )}
              {!testMode&&results?.journeys?.length>0 && (
                <div style={journeyBox}>
                  <div style={{ display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:6 }}>
                    <b style={{ fontSize:11 }}>Vehicle Journeys ({results.journeys.length})</b>
                  </div>
                  {results.journeys.slice(0,5).map(j=>(
                    <div key={j.id} style={journeyRow}>
                      <div style={{ flex:1,minWidth:0 }}>
                        <b style={{ fontSize:11 }}>{j.sighting_count} sighting{j.sighting_count===1?'':'s'}</b>
                        <div style={{ ...muted,marginTop:2 }}>{fmt(j.started_at)} → {j.ended_at?fmt(j.ended_at):'ongoing'}</div>
                        <div style={{ ...muted,marginTop:1 }}>Confidence: {j.journey_confidence!=null?`${(Number(j.journey_confidence)*100).toFixed(0)}%`:'—'} · Status: {j.status}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {results?.detections?.length
                ?results.detections.map(d=><SightingCard key={d.id} d={d} journeyLoading={journeyLoading} onShowJourney={showJourney}/>)
                :results?<div style={empty}>No confirmed sightings found.</div>:null}
            </main>
          </>
        ) : (
          <main style={body}>
            <div style={uploadBox}>
              <div style={{ display:'flex',alignItems:'center',gap:9 }}>
                <span style={iconBox}><UserIcon /></span>
                <div><b>Person reference photos</b><div style={muted}>Upload at least one photo with a visible face. Each image is normalized before InsightFace detection.</div></div>
              </div>
              <input id="person-reference-upload-v2" type="file" accept="image/*" multiple onChange={addPhotos} style={{ display:'none' }} />
              <label htmlFor="person-reference-upload-v2" style={uploadBtn}>+ Add Photos</label>
              {personFiles.length>0 && (
                <div style={photoGrid}>
                  {personFiles.map((file,i)=>{
                    const v=personValidation[i]
                    return (
                      <div key={`${file.name}-${file.lastModified}-${i}`}
                           style={{ position:'relative',background:'#000',borderRadius:8,overflow:'hidden',border:`1px solid ${v?.valid?'var(--green)':v?.valid===false?'var(--high)':'var(--border)'}` }}>
                        <img src={previewUrls[i]} alt={`Reference ${i+1}`} style={{ display:'block',width:'100%',height:120,objectFit:'cover' }} />
                        <span style={{ position:'absolute',left:5,right:5,bottom:5,padding:'4px 6px',borderRadius:5,background:'rgba(0,0,0,.78)',fontSize:9,color:v?.valid?'var(--green)':v?.valid===false?'var(--high)':'var(--text2)' }}>
                          {personChecking&&!v?'Checking…':v?.valid?`Face detected · ${v.face_count}`:v?`No visible face · ${v.message||'Rejected'}`:'Pending'}
                        </span>
                        <button onClick={()=>setPersonFiles(c=>c.filter((_,n)=>n!==i))} style={removeBtn} aria-label="Remove photo">×</button>
                      </div>
                    )
                  })}
                </div>
              )}
              <div style={{ marginTop:12,...muted }}>{personFiles.length} selected · {validCount} valid</div>
              {error && <div style={errorBox}>{error}</div>}
              {personResults && (
                <div style={personResults.status==='matches'?matchBox:empty}>
                  <b>{personResults.status==='matches'?'Face matches':'No face matches'}</b>
                  {personResults.matches?.length>0&&personResults.matches.slice(0,20).map((m,i)=>(
                    <div key={`${m.id}-${i}`} style={{...matchRow,flexWrap:'wrap'}}>
                      <div style={{display:'flex',gap:10,alignItems:'center',flex:1,minWidth:0}}>
                        {previewUrls[0]&&<img src={previewUrls[0]} alt="Reference" style={{width:72,height:54,objectFit:'cover',borderRadius:6,border:'1px solid var(--border)'}}/>}
                        {m.sighting_evidence?.thumbnail_url||m.sighting_evidence?.frame_url
                          ? <img src={m.sighting_evidence.thumbnail_url||m.sighting_evidence.frame_url} alt="Sighting" style={{width:72,height:54,objectFit:'cover',borderRadius:6,border:'1px solid var(--accent-border)'}}/>
                          : <div style={{width:72,height:54,borderRadius:6,border:'1px dashed var(--border)',display:'grid',placeItems:'center',fontSize:8,color:'var(--text2)'}}>No frame</div>}
                        <span style={{ flex:1,minWidth:0 }}>{m.entity_type||'Person'} · {m.first_seen_cam||m.first_camera_label||'Camera'}</span>
                      </div>
                      <ScoreBadge label="Match" value={Number(m.similarity||0)} color="var(--green)" />
                      {personResults.threshold!=null && <span style={muted}>Threshold: {(Number(personResults.threshold)*100).toFixed(0)}%</span>}
                    </div>
                  ))}
                </div>
              )}
              <div style={{ display:'flex',justifyContent:'flex-end',marginTop:13 }}>
                <Button disabled={!validCount||personChecking||personSearching} onClick={runPersonInvestigation}
                        style={{ minHeight:38,padding:'0 20px',fontSize:12,fontWeight:800,display:'inline-flex',alignItems:'center',gap:6 }}>
                  <SearchIcon />{personSearching?'Searching…':personResults?.status==='matches'?'Search Again':'Find Face Matches'}
                </Button>
              </div>
            </div>
          </main>
        )}
      </section>
    </div>
  )
}

const overlay={position:'fixed',inset:0,background:'color-mix(in srgb,var(--bg) 82%,transparent)',display:'flex',alignItems:'center',justifyContent:'center',zIndex:1000,padding:16}
const modal={background:'var(--surface)',borderRadius:13,border:'1px solid var(--border)',width:'min(900px,96vw)',maxHeight:'90vh',display:'flex',flexDirection:'column',overflow:'hidden',boxShadow:'var(--shadow)',color:'var(--text)'}
const head={padding:'17px 19px',borderBottom:'1px solid var(--border)',display:'flex',justifyContent:'space-between',alignItems:'center'}
const sub={fontSize:10,color:'var(--text2)',marginTop:3}
const close={width:34,height:34,display:'grid',placeItems:'center',border:'1px solid var(--border)',borderRadius:8,background:'var(--surface2)',color:'var(--text2)',cursor:'pointer'}
const toolbar={display:'flex',gap:8,padding:'14px 19px 6px',alignItems:'center'}
const helper={padding:'0 19px 10px',fontSize:9,color:'var(--text2)'}
const body={flex:1,overflowY:'auto',padding:'8px 19px 18px',minHeight:0}
const muted={fontSize:10,color:'var(--text2)',marginTop:3}
const empty={padding:30,textAlign:'center',color:'var(--text2)',fontSize:11}
const errorBox={padding:9,borderRadius:7,border:'1px solid color-mix(in srgb,var(--red) 35%,transparent)',background:'color-mix(in srgb,var(--red) 8%,transparent)',color:'var(--red)',fontSize:10,marginBottom:9}
const watchlistBox={padding:10,borderRadius:8,border:'1px solid var(--red)',background:'color-mix(in srgb,var(--red) 8%,transparent)',fontSize:11,marginBottom:10,color:'var(--text)'}
const journeyBox={padding:10,borderRadius:8,border:'1px solid var(--accent-border)',background:'var(--accent-soft)',fontSize:11,marginBottom:10}
const journeyRow={display:'flex',alignItems:'flex-start',gap:8,padding:'7px 0',borderBottom:'1px solid var(--border)'}
const matchBox={padding:12,borderRadius:8,border:'1px solid var(--green)',background:'color-mix(in srgb,var(--green) 7%,transparent)',fontSize:11,marginBottom:10}
const matchRow={display:'flex',alignItems:'center',gap:8,padding:'8px 0',borderBottom:'1px solid var(--border)'}
const uploadBox={padding:17,border:'1px dashed var(--accent-border)',borderRadius:10,background:'var(--accent-soft)'}
const iconBox={width:38,height:38,borderRadius:9,display:'grid',placeItems:'center',background:'var(--accent-soft)',color:'var(--accent-strong)'}
const uploadBtn={display:'inline-flex',alignItems:'center',gap:6,marginTop:15,padding:'9px 14px',borderRadius:7,background:'var(--accent)',color:'var(--on-accent)',border:'1px solid var(--accent)',fontSize:11,fontWeight:850,cursor:'pointer',boxShadow:'0 4px 12px rgba(0,0,0,.15)'}
const photoGrid={display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(130px,1fr))',gap:9,marginTop:13}
const removeBtn={position:'absolute',top:5,right:5,width:23,height:23,border:0,borderRadius:6,background:'rgba(0,0,0,.75)',color:'#fff',fontSize:13,lineHeight:1,cursor:'pointer',display:'grid',placeItems:'center'}

function fmt(v) { if(!v) return '—'; const d=typeof v==='number'?new Date(v*1000):new Date(v); return Number.isNaN(d.getTime())?'—':d.toLocaleString('en-IN',{hour12:false}) }
