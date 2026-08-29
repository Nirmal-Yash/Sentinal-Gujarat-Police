import { useEffect, useState } from 'react'

const ShieldIcon = () => <svg width="28" height="28" viewBox="0 0 24 24" fill="var(--accent)" aria-hidden="true"><path d="M12 2L3 6v6c0 5.25 3.75 10.15 9 11.25C17.25 22.15 21 17.25 21 12V6L12 2z"/><path d="M9 12l2 2 4-4" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" fill="none"/></svg>
const SearchIcon = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
const ListIcon = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
const BellIcon = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg>
const CameraIcon = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M15 10l4.5-2.1A1 1 0 0121 8.8v6.4a1 1 0 01-1.5.9L15 14"/><rect x="2" y="6" width="13" height="12" rx="2"/></svg>
const MapIcon = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m9 18-6 3V6l6-3 6 3 6-3v15l-6 3-6-3Z"/><path d="M9 3v15M15 6v15"/></svg>

const btn = { display:'inline-flex', alignItems:'center', justifyContent:'center', gap:6, minHeight:32, padding:'0 10px', borderRadius:7, border:'1px solid var(--border)', background:'rgba(255,255,255,.01)', color:'var(--text)', cursor:'pointer', fontSize:11, fontWeight:600, transition:'all .16s ease', letterSpacing:.2, textDecoration:'none', whiteSpace:'nowrap' }
const routeButton = active => ({ ...btn, background: active ? 'rgba(88,166,255,.10)' : 'rgba(255,255,255,.01)', borderColor: active ? 'rgba(88,166,255,.55)' : 'var(--border)', color: active ? 'var(--accent)' : 'var(--text)' })
const routeItems = [['/dashboard','Dashboard',CameraIcon],['/feeds','Feeds',CameraIcon],['/map','Map',MapIcon],['/alerts','Alerts',BellIcon],['/investigations','Investigate',SearchIcon]]

export default function Navbar({ alertCount, onSearchOpen, onWatchlistOpen, onOnboardOpen, onVendorsOpen, onTestOpen, testMode, onReportExport, principal, onLogout, path='/', onNavigate }) {
  const [time,setTime] = useState(new Date())
  useEffect(()=>{ const t=setInterval(()=>setTime(new Date()),1000); return()=>clearInterval(t) },[])
  const go = target => event => { event.preventDefault(); if (target === '/alerts') window.dispatchEvent(new CustomEvent('sentinel:open-alerts')); onNavigate?.(target) }
  const timeStr=time.toLocaleTimeString('en-IN',{hour12:false}), dateStr=time.toLocaleDateString('en-IN',{day:'2-digit',month:'short',year:'numeric'})
  const admin = principal && ['ADMIN','SUPERADMIN'].includes(principal.role)
  return <nav style={{ display:'flex', alignItems:'center', gap:8, padding:'0 14px', minHeight:56, flexShrink:0, background:'linear-gradient(180deg,rgba(22,27,34,.98),rgba(13,17,23,.98))', borderBottom:'1px solid var(--border)', overflowX:'auto' }}>
    <div style={{ display:'flex', alignItems:'center', gap:9, minWidth:215 }}><div style={{ width:34,height:34,display:'grid',placeItems:'center',border:'1px solid var(--border)',borderRadius:8,background:'rgba(88,166,255,.07)' }}><ShieldIcon/></div><div style={{ lineHeight:1.15 }}><div style={{ fontSize:13,fontWeight:850,letterSpacing:.9 }}>SENTINEL AI</div><div style={{ fontSize:8,color:'var(--text2)',letterSpacing:.7,textTransform:'uppercase',marginTop:3 }}>Gujarat Police Operations</div></div></div>
    <div style={{ width:1,height:28,background:'var(--border)',flexShrink:0 }}/>
    <div style={{ display:'flex',alignItems:'center',gap:5,padding:'0 6px',height:28,border:'1px solid rgba(63,185,80,.22)',borderRadius:6,background:'rgba(63,185,80,.06)' }}><span className="sentinel-live-pulse" style={{ width:6,height:6,borderRadius:'50%',background:'var(--green)',boxShadow:'0 0 8px var(--green)' }}/><span style={{ fontSize:9,color:'var(--green)',fontWeight:800,letterSpacing:.6 }}>LIVE</span></div>
    <div style={{ fontSize:10,color:'var(--text2)',fontVariantNumeric:'tabular-nums',whiteSpace:'nowrap' }}>{timeStr}<span style={{ opacity:.55,marginLeft:6 }}>{dateStr}</span></div>
    <div style={{ display:'flex',gap:5,marginLeft:4 }}>{routeItems.map(([href,label,Icon]) => <a key={href} href={href} onClick={go(href)} title={label} style={routeButton(path===href)}><Icon/><span>{label}</span>{href==='/alerts'&&alertCount>0?<span style={{ minWidth:16,padding:'1px 4px',borderRadius:10,background:'var(--high)',color:'#fff',fontSize:8,fontWeight:800 }}>{Math.min(alertCount,99)}</span>:null}</a>)}</div>
    <div style={{ flex:1,minWidth:10 }}/>
    <button style={btn} onClick={onSearchOpen} title="Search"><SearchIcon/><span>Search</span></button>
    <button style={btn} onClick={onWatchlistOpen} title="Watchlist"><ListIcon/><span>Watchlist</span></button>
    {admin&&<><button style={btn} onClick={onOnboardOpen} title="Add camera">Add camera</button><button style={btn} onClick={onVendorsOpen} title="Vendor and model management">Vendors</button><button style={btn} onClick={onReportExport} title="Export detections">Export</button></>}
    {admin&&onTestOpen&&<a href="/test" onClick={event=>{event.preventDefault();onNavigate?.('/test');onTestOpen()}} title="Isolated demonstration environment" style={{ ...routeButton(path==='/test'||testMode), color:testMode?'var(--accent)':'var(--text)' }}>{testMode?'Exit test':'Test mode'}</a>}
    {principal&&<div style={{ display:'flex',alignItems:'center',gap:7,padding:'4px 7px',border:'1px solid var(--border)',borderRadius:7,background:'rgba(255,255,255,.02)',whiteSpace:'nowrap' }}><div style={{ width:24,height:24,borderRadius:6,display:'grid',placeItems:'center',background:'var(--surface2)',fontSize:10,fontWeight:800,color:'var(--accent)' }}>{String(principal.username||'?').slice(0,1).toUpperCase()}</div><span style={{ fontSize:10,color:'var(--text2)' }}>{principal.username} · {principal.role}</span></div>}
    {principal?.id&&<button style={btn} onClick={onLogout}>Sign out</button>}
  </nav>
}
