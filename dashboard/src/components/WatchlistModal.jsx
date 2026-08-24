import { useState, useEffect } from 'react'
import { api } from '../api/client'

const overlay = {
  position:'fixed',inset:0,background:'rgba(0,0,0,.7)',
  display:'flex',alignItems:'center',justifyContent:'center',zIndex:1000,
}
const modal = {
  background:'var(--surface)',borderRadius:10,border:'1px solid var(--border)',
  width:'min(560px,95vw)',maxHeight:'80vh',display:'flex',flexDirection:'column',
  overflow:'hidden',
}

const EMPTY = { name:'', entity_type:'person', description:'', plate_number:'', alert_priority:'HIGH' }

export default function WatchlistModal({ onClose }) {
  const [entries, setEntries] = useState([])
  const [form,    setForm]    = useState(EMPTY)
  const [loading, setLoading] = useState(false)
  const [tab,     setTab]     = useState('list')

  useEffect(() => { load() }, [])

  const load = async () => {
    try { setEntries(await api.getWatchlist()) } catch {}
  }

  const submit = async () => {
    if (!form.name.trim()) return
    setLoading(true)
    try {
      await api.addWatchlist({
        ...form,
        plate_number: form.plate_number?.trim()||null,
      })
      setForm(EMPTY)
      await load()
      setTab('list')
    } catch(e) {
      alert(e.message)
    } finally {
      setLoading(false)
    }
  }

  const remove = async (id) => {
    if (!confirm('Deactivate this entry?')) return
    await api.removeWatchlist(id)
    await load()
  }

  const inp = (field,placeholder,type='text') => (
    <input type={type} placeholder={placeholder} value={form[field]}
      onChange={e=>setForm(f=>({...f,[field]:e.target.value}))}
      style={{width:'100%',padding:'8px 10px',borderRadius:6,marginBottom:8,
              border:'1px solid var(--border)',background:'var(--surface2)',
              color:'var(--text)',fontSize:13}}/>
  )

  return (
    <div style={overlay} onClick={e=>e.target===e.currentTarget&&onClose()}>
      <div style={modal}>
        {/* Header */}
        <div style={{padding:'14px 18px',borderBottom:'1px solid var(--border)',
                     display:'flex',justifyContent:'space-between',alignItems:'center'}}>
          <span style={{fontWeight:700,fontSize:15}}>Watchlist</span>
          <button onClick={onClose} style={{background:'none',border:'none',
            color:'var(--text2)',cursor:'pointer',fontSize:20}}>×</button>
        </div>

        {/* Tabs */}
        <div style={{display:'flex',borderBottom:'1px solid var(--border)'}}>
          {[['list','View All'],['add','+ Add Entry']].map(([t,l])=>(
            <button key={t} onClick={()=>setTab(t)}
              style={{flex:1,padding:'9px 0',border:'none',
                      borderBottom:`2px solid ${tab===t?'var(--accent)':'transparent'}`,
                      background:'transparent',
                      color:tab===t?'var(--accent)':'var(--text2)',
                      cursor:'pointer',fontSize:13}}>
              {l}
            </button>
          ))}
        </div>

        <div style={{flex:1,overflowY:'auto',padding:18}}>
          {tab==='list' && (
            <>
              <div style={{fontSize:13,color:'var(--text2)',marginBottom:10}}>
                {entries.length} active entries
              </div>
              {entries.map(e=>(
                <div key={e.id} style={{
                  padding:'10px 12px',marginBottom:8,borderRadius:8,
                  background:'var(--surface2)',border:'1px solid var(--border)',
                  display:'flex',gap:10,alignItems:'flex-start',
                }}>
                  <div style={{fontSize:20}}>{e.entity_type==='vehicle'?'V':'P'}</div>
                  <div style={{flex:1,minWidth:0}}>
                    <div style={{fontWeight:600,fontSize:13,marginBottom:2}}>{e.name}</div>
                    {e.plate_number&&<div style={{fontSize:12,color:'var(--accent)'}}>
                      Plate: {e.plate_number}
                    </div>}
                    {e.description&&<div style={{fontSize:12,color:'var(--text2)',
                                                marginTop:2}}>{e.description}</div>}
                  </div>
                  <div style={{display:'flex',flexDirection:'column',alignItems:'flex-end',gap:4}}>
                    <span style={{fontSize:10,fontWeight:700,
                                  color: e.alert_priority==='HIGH'?'var(--high)':'var(--medium)',
                                  background: (e.alert_priority==='HIGH'?'var(--high)':'var(--medium)')+'22',
                                  padding:'1px 6px',borderRadius:4}}>
                      {e.alert_priority}
                    </span>
                    <button onClick={()=>remove(e.id)}
                      style={{fontSize:11,padding:'2px 8px',borderRadius:4,
                              border:'1px solid var(--border)',background:'transparent',
                              color:'var(--red)',cursor:'pointer'}}>
                      Remove
                    </button>
                  </div>
                </div>
              ))}
              {entries.length===0&&(
                <div style={{textAlign:'center',padding:32,color:'var(--text2)',fontSize:13}}>
                  Watchlist empty
                </div>
              )}
            </>
          )}

          {tab==='add' && (
            <div>
              <label style={{fontSize:12,color:'var(--text2)',display:'block',marginBottom:4}}>
                Full Name *
              </label>
              {inp('name','Suspect / Vehicle name')}
              <label style={{fontSize:12,color:'var(--text2)',display:'block',marginBottom:4}}>
                Type
              </label>
              <select value={form.entity_type}
                onChange={e=>setForm(f=>({...f,entity_type:e.target.value}))}
                style={{width:'100%',padding:'8px 10px',borderRadius:6,marginBottom:8,
                        border:'1px solid var(--border)',background:'var(--surface2)',
                        color:'var(--text)',fontSize:13}}>
                <option value="person">Person</option>
                <option value="vehicle">Vehicle</option>
              </select>
              {inp('plate_number','License plate (for vehicles, e.g. GJ03AA1234)')}
              {inp('description','Description / notes')}
              <label style={{fontSize:12,color:'var(--text2)',display:'block',marginBottom:4}}>
                Alert Priority
              </label>
              <select value={form.alert_priority}
                onChange={e=>setForm(f=>({...f,alert_priority:e.target.value}))}
                style={{width:'100%',padding:'8px 10px',borderRadius:6,marginBottom:16,
                        border:'1px solid var(--border)',background:'var(--surface2)',
                        color:'var(--text)',fontSize:13}}>
                <option>HIGH</option><option>MEDIUM</option><option>LOW</option>
              </select>
              <button onClick={submit} disabled={loading}
                style={{width:'100%',padding:'10px',borderRadius:6,border:'none',
                        background:'var(--accent)',color:'#fff',fontWeight:700,
                        fontSize:14,cursor:'pointer',opacity:loading?.6:1}}>
                {loading?'Adding…':'Add to Watchlist'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
