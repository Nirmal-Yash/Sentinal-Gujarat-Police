import { useEffect, useState } from 'react'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { SidebarProvider, Sidebar, SidebarHeader, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupLabel, SidebarGroupContent, SidebarMenu, SidebarMenuItem, SidebarMenuButton, SidebarTrigger } from './ui/sidebar'
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator } from './ui/dropdown-menu'

const SearchIcon=()=> <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
const BellIcon=()=> <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 0-3.46 0"/></svg>
const CameraIcon=()=> <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M15 10l4.5-2.1A1 1 0 0121 8.8v6.4a1 1 0 01-1.5.9L15 14"/><rect x="2" y="6" width="13" height="12" rx="2"/></svg>
const MapIcon=()=> <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m9 18-6 3V6l6-3 6 3 6-3v15l-6 3-6-3Z"/><path d="M9 3v15M15 6v15"/></svg>
const SearchNavIcon=()=> <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
const ShieldIcon=()=> <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M12 3 5 6v5c0 4.7 2.8 8.2 7 10 4.2-1.8 7-5.3 7-10V6l-7-3Z"/><path d="m9.5 12 1.7 1.8 3.7-4"/></svg>
const ChevronDown=()=> <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>

const routeItems=[['/feeds','Live Monitoring',CameraIcon],['/map','GIS Map',MapIcon],['/investigations','Investigate',SearchNavIcon],['/alerts','Alerts',BellIcon]]

export default function Navbar({ alertCount=0,onSearchOpen,onWatchlistOpen,onOnboardOpen,onVendorsOpen,onTestOpen,testMode,onReportExport,principal,onLogout,path='/',onNavigate }) {
 const [time,setTime]=useState(new Date()), [sidebarOpen,setSidebarOpen]=useState(()=>localStorage.getItem('sentinel.sidebar.open.v1')!=='false'), [search,setSearch]=useState('')
 useEffect(()=>{const t=setInterval(()=>setTime(new Date()),1000);return()=>clearInterval(t)},[])
 useEffect(()=>{localStorage.setItem('sentinel.sidebar.open.v1',String(sidebarOpen))},[sidebarOpen])
 const go=target=>event=>{event.preventDefault();onNavigate?.(target)}
 const submitSearch=event=>{event.preventDefault();if(search.trim()){onSearchOpen?.(search.trim());setSearch('')}else onSearchOpen?.()}
 const admin=principal&&['ADMIN','SUPERADMIN'].includes(principal.role)
 return <SidebarProvider defaultOpen={sidebarOpen} onOpenChange={setSidebarOpen}>
   <Sidebar>
     <SidebarHeader>
       <a href="/feeds" onClick={go('/feeds')} className="ui-sidebar-brand" aria-label="Sentinel AI home">
         <span className="ui-sidebar-brand-mark"><ShieldIcon/></span>
         <span className="ui-sidebar-header-text"><div className="ui-sidebar-brand-title">SENTINEL AI</div><div className="ui-sidebar-brand-sub">Gujarat Police Operations</div></span>
       </a>
       <div style={{display:'flex',justifyContent:'flex-end',marginTop:9}}><SidebarTrigger/></div>
     </SidebarHeader>
     <SidebarContent>
       <SidebarGroup><SidebarGroupLabel>Operations</SidebarGroupLabel><SidebarGroupContent><SidebarMenu>
         {routeItems.map(([href,label,Icon])=><SidebarMenuItem key={href}><SidebarMenuButton href={href} onClick={go(href)} active={path===href} tooltip={label}><Icon/><span>{label}{href==='/alerts'&&alertCount>0?` · ${Math.min(alertCount,99)}`:''}</span></SidebarMenuButton></SidebarMenuItem>)}
       </SidebarMenu></SidebarGroupContent></SidebarGroup>
       <SidebarGroup><SidebarGroupLabel>Management</SidebarGroupLabel><SidebarGroupContent><SidebarMenu>
         <SidebarMenuItem><SidebarMenuButton href="#" onClick={e=>{e.preventDefault();onWatchlistOpen?.()}} tooltip="Watchlist"><SearchNavIcon/><span>Watchlist</span></SidebarMenuButton></SidebarMenuItem>
         {admin&&<><SidebarMenuItem><SidebarMenuButton href="#" onClick={e=>{e.preventDefault();onOnboardOpen?.()}} tooltip="Camera Registry"><CameraIcon/><span>Camera Registry</span></SidebarMenuButton></SidebarMenuItem><SidebarMenuItem><SidebarMenuButton href="#" onClick={e=>{e.preventDefault();onVendorsOpen?.()}} tooltip="Vendors"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 7h16M4 12h16M4 17h10"/></svg><span>Vendors & Models</span></SidebarMenuButton></SidebarMenuItem></>}
         {admin&&onTestOpen&&<SidebarMenuItem><SidebarMenuButton href="/test" onClick={e=>{e.preventDefault();onNavigate?.('/test');onTestOpen()}} active={path==='/test'||testMode} tooltip="Test Mode"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M8 3h8M9 3v5l-4 7a4 4 0 0 0 3.5 6h7A4 4 0 0 0 19 15l-4-7V3"/><path d="M7 15h10"/></svg><span>{testMode?'Exit Test Mode':'Test Mode'}</span></SidebarMenuButton></SidebarMenuItem>}
       </SidebarMenu></SidebarGroupContent></SidebarGroup>
     </SidebarContent>
     <SidebarFooter>
       {principal?.id&&<DropdownMenu>
         <DropdownMenuTrigger asChild><button type="button" className="sentinel-user-trigger" title="User profile"><span className="sentinel-avatar">{String(principal.username||'?').slice(0,1).toUpperCase()}</span><span className="ui-sidebar-footer-text sentinel-user-meta"><span className="sentinel-user-name">{principal.username}</span><span className="sentinel-user-role">{principal.role}</span></span><ChevronDown/></button></DropdownMenuTrigger>
         <DropdownMenuContent align="start"><DropdownMenuLabel>Signed in</DropdownMenuLabel><DropdownMenuItem disabled>{principal.username} · {principal.role}</DropdownMenuItem><DropdownMenuSeparator/><DropdownMenuItem onSelect={onLogout}>Sign out</DropdownMenuItem></DropdownMenuContent>
       </DropdownMenu>}
     </SidebarFooter>
   </Sidebar>
   <div className="sentinel-main">
     <header className="sentinel-topbar">
       <div className="sentinel-topbar-mobile-trigger"><SidebarTrigger/></div>
       <div className="sentinel-topbar-title-wrap"><div className="sentinel-topbar-title">{path==='/map'?'GIS Command Map':path==='/investigations'?'Vehicle Investigation':path==='/alerts'?'Alert Operations':path==='/test'?'Demonstration Environment':'Live Monitoring'}</div><div className="sentinel-topbar-sub">Gujarat State CCTV Intelligence Platform</div></div>
       <form className="sentinel-search-wrap" onSubmit={submitSearch}><span className="sentinel-search-icon"><SearchIcon/></span><Input value={search} onChange={e=>setSearch(e.target.value)} className="sentinel-search-input" placeholder="Search camera, plate, track or investigation…" aria-label="Search Sentinel"/><span className="sentinel-search-hint">Enter</span></form>
       <div className="sentinel-topbar-actions">
         <span className="sentinel-status"><span className="sentinel-live-pulse"/>SYSTEM ONLINE</span>
         {alertCount>0&&<Button variant="ghost" size="sm" title={`${alertCount} unacknowledged alerts`} onClick={()=>{onNavigate?.('/alerts');window.dispatchEvent(new CustomEvent('sentinel:open-alerts'))}}><BellIcon/><span>{Math.min(alertCount,99)}</span></Button>}
         <div className="sentinel-clock">{time.toLocaleTimeString('en-IN',{hour12:false})}</div>
       </div>
     </header>
   </div>
 </SidebarProvider>
}
