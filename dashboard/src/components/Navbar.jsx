import { useEffect, useState } from 'react'
import { api } from '../api/client'

const ShieldIcon = () => (
  <svg width="26" height="26" viewBox="0 0 24 24" fill="var(--accent)">
    <path d="M12 2L3 6v6c0 5.25 3.75 10.15 9 11.25C17.25 22.15 21 17.25 21 12V6L12 2z"/>
    <path d="M9 12l2 2 4-4" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
  </svg>
)

const SearchIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
  </svg>
)

const ListIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/>
    <line x1="8" y1="18" x2="21" y2="18"/>
    <line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/>
    <line x1="3" y1="18" x2="3.01" y2="18"/>
  </svg>
)

const BellIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/>
    <path d="M13.73 21a2 2 0 01-3.46 0"/>
  </svg>
)

const btn = {
  display: 'flex', alignItems: 'center', gap: 6,
  padding: '5px 12px', borderRadius: 6,
  border: '1px solid var(--border)',
  background: 'transparent', color: 'var(--text)',
  cursor: 'pointer', fontSize: 12, fontWeight: 500,
  transition: 'background .15s, border-color .15s',
  letterSpacing: .2,
}

export default function Navbar({ alertCount, onSearchOpen, onWatchlistOpen, onOnboardOpen, onVendorsOpen, onTestOpen, onReportExport, principal, onLogout, mapExpanded, onMapView, onGridView }) {
  const [time, setTime] = useState(new Date())

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  const timeStr = time.toLocaleTimeString('en-IN', { hour12: false })
  const dateStr = time.toLocaleDateString('en-IN', { day:'2-digit', month:'short', year:'numeric' })

  return (
    <nav style={{
      display: 'flex', alignItems: 'center', gap: 12,
      padding: '0 16px', height: 52, flexShrink: 0,
      background: 'var(--surface)',
      borderBottom: '1px solid var(--border)',
    }}>
      {/* Brand */}
      <ShieldIcon/>
      <div style={{ lineHeight: 1.2 }}>
        <div style={{ fontSize: 14, fontWeight: 800, letterSpacing: .8, color: 'var(--text)' }}>
          SENTINEL AI
        </div>
        <div style={{ fontSize: 9, color: 'var(--text2)', letterSpacing: .6, textTransform: 'uppercase' }}>
          Gujarat Police Innovation Challenge 2026
        </div>
      </div>

      {/* Divider */}
      <div style={{ width: 1, height: 28, background: 'var(--border)', marginLeft: 4 }}/>

      {/* Live indicator */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{
          width: 7, height: 7, borderRadius: '50%',
          background: 'var(--green)', boxShadow: '0 0 7px var(--green)',
          animation: 'navPulse 2s ease-in-out infinite',
        }}/>
        <span style={{ fontSize: 11, color: 'var(--green)', fontWeight: 700, letterSpacing: .5 }}>
          LIVE
        </span>
      </div>

      {/* Clock */}
      <div style={{ fontSize: 12, color: 'var(--text2)', fontVariantNumeric: 'tabular-nums' }}>
        {timeStr} &nbsp;
        <span style={{ fontSize: 11, color: 'var(--text2)', opacity: .7 }}>{dateStr}</span>
      </div>

      {/* Spacer */}
      <div style={{ flex: 1 }}/>

      {/* Unacknowledged alert badge */}
      {alertCount > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          background: 'rgba(248,81,73,.12)', border: '1px solid rgba(248,81,73,.3)',
          borderRadius: 6, padding: '4px 10px',
        }}>
          <BellIcon/>
          <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--high)' }}>
            {alertCount} unacknowledged
          </span>
        </div>
      )}

      {/* Action buttons */}
      <button style={btn} onClick={onSearchOpen}
        onMouseEnter={e => e.currentTarget.style.background = 'var(--surface2)'}
        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
        <SearchIcon/> Search
      </button>
      <button style={btn} onClick={onWatchlistOpen}
        onMouseEnter={e => e.currentTarget.style.background = 'var(--surface2)'}
        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
        <ListIcon/> Watchlist
      </button>
      <button style={{ ...btn, background: mapExpanded ? 'var(--surface2)' : 'transparent' }} onClick={onMapView}>Map</button>
      <button style={{ ...btn, background: !mapExpanded ? 'var(--surface2)' : 'transparent' }} onClick={onGridView}>Feeds</button>
      {principal && ['ADMIN', 'SUPERADMIN'].includes(principal.role) && <>
        <button style={btn} onClick={onOnboardOpen}>Add camera</button>
        <button style={btn} onClick={onVendorsOpen}>Vendors</button>
        <button style={btn} onClick={onReportExport}>Export detections</button>
      </>}
      {principal?.role === 'SUPERADMIN' && onTestOpen && <button style={btn} onClick={onTestOpen}>Test diagnostics</button>}
      {principal && <span style={{ padding: '4px 8px', borderRadius: 5, background: 'var(--surface2)', color: 'var(--text2)', fontSize: 10 }}>{principal.username} · {principal.role}</span>}
      {principal?.id && <button style={btn} onClick={onLogout}>Sign out</button>}

      <style>{`@keyframes navPulse { 0%,100%{opacity:1} 50%{opacity:.4} }`}</style>
    </nav>
  )
}
