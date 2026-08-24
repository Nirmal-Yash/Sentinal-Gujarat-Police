import { useState } from 'react'
import { api } from '../api/client'

const overlay = {
  position:'fixed',inset:0,background:'rgba(0,0,0,.7)',
  display:'flex',alignItems:'center',justifyContent:'center',zIndex:1000,
}
const modal = {
  background:'var(--surface)',borderRadius:10,border:'1px solid var(--border)',
  width:'min(600px,95vw)',maxHeight:'80vh',display:'flex',flexDirection:'column',
  overflow:'hidden',
}

export default function SearchModal({ onClose }) {
  const [tab,     setTab]     = useState('plate')
  const [query,   setQuery]   = useState('')
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState('')

  const search = async () => {
    if (!query.trim()) return
    setLoading(true); setError(''); setResults(null)
    try {
      const data = tab === 'plate'
        ? await api.searchPlate(query)
        : await api.searchTrack(query)
      setResults(data)
    } catch(e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={overlay} onClick={e=>e.target===e.currentTarget&&onClose()}>
      <div style={modal}>
        {/* Header */}
        <div style={{padding:'14px 18px',borderBottom:'1px solid var(--border)',
                     display:'flex',justifyContent:'space-between',alignItems:'center'}}>
          <span style={{fontWeight:700,fontSize:15}}>Search</span>
          <button onClick={onClose} style={{background:'none',border:'none',
            color:'var(--text2)',cursor:'pointer',fontSize:20}}>×</button>
        </div>

        {/* Tabs */}
        <div style={{display:'flex',borderBottom:'1px solid var(--border)'}}>
          {['plate','track'].map(t=>(
            <button key={t} onClick={()=>setTab(t)}
              style={{flex:1,padding:'9px 0',border:'none',
                      borderBottom:`2px solid ${tab===t?'var(--accent)':'transparent'}`,
                      background:'transparent',
                      color: tab===t?'var(--accent)':'var(--text2)',
                      cursor:'pointer',fontSize:13}}>
              {t==='plate'?'License Plate':'Global Track ID'}
            </button>
          ))}
        </div>

        {/* Input */}
        <div style={{padding:'14px 18px',display:'flex',gap:8}}>
          <input
            value={query} onChange={e=>setQuery(e.target.value)}
            onKeyDown={e=>e.key==='Enter'&&search()}
            placeholder={tab==='plate'?'e.g. GJ03AA1234':'e.g. GT-ABCD1234'}
            style={{flex:1,padding:'8px 12px',borderRadius:6,border:'1px solid var(--border)',
                    background:'var(--surface2)',color:'var(--text)',fontSize:13}}
          />
          <button onClick={search} disabled={loading}
            style={{padding:'8px 18px',borderRadius:6,border:'none',
                    background:'var(--accent)',color:'#fff',cursor:'pointer',
                    fontSize:13,fontWeight:600,opacity:loading?.6:1}}>
            {loading?'…':'Search'}
          </button>
        </div>

        {/* Results */}
        <div style={{flex:1,overflowY:'auto',padding:'0 18px 18px'}}>
          {error && <div style={{color:'var(--red)',fontSize:13}}>{error}</div>}

          {results && tab==='plate' && (
            <>
              {results.watchlist_hits.length>0 && (
                <div style={{marginBottom:12,padding:10,borderRadius:6,
                             background:'var(--red)22',border:'1px solid var(--red)'}}>
                  <div style={{fontWeight:700,color:'var(--red)',fontSize:13,marginBottom:4}}>
                    Watchlist Match
                  </div>
                  {results.watchlist_hits.map((h,i)=>(
                    <div key={i} style={{fontSize:12,color:'var(--text)'}}>
                      {h.name} — {h.description} [{h.alert_priority}]
                    </div>
                  ))}
                </div>
              )}
              <div style={{fontSize:13,color:'var(--text2)',marginBottom:8}}>
                {results.detections.length} sighting(s) found
              </div>
              {results.detections.map((d,i)=>(
                <div key={i} style={{padding:'8px 10px',marginBottom:6,borderRadius:6,
                                     background:'var(--surface2)',
                                     border:'1px solid var(--border)',fontSize:12}}>
                  <b>{d.plate_text}</b> — {d.cam_name}
                  <span style={{color:'var(--text2)',marginLeft:8}}>
                    {new Date(d.timestamp).toLocaleString()}
                  </span>
                </div>
              ))}
            </>
          )}

          {results && tab==='track' && (
            <>
              <div style={{fontSize:13,color:'var(--text2)',marginBottom:8}}>
                {results.sightings.length} sighting(s) for track {results.global_track_id}
              </div>
              {results.sightings.map((s,i)=>(
                <div key={i} style={{padding:'8px 10px',marginBottom:6,borderRadius:6,
                                     background:'var(--surface2)',
                                     border:'1px solid var(--border)',fontSize:12,
                                     display:'flex',gap:10,alignItems:'center'}}>
                  <span style={{color:'var(--accent)',fontWeight:600}}>→</span>
                  <div>
                    <b>{s.cam_name}</b>
                    <span style={{color:'var(--text2)',marginLeft:8}}>
                      {new Date(s.timestamp).toLocaleString()}
                    </span>
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
