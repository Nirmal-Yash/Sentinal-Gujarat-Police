import { useState, useEffect } from 'react'
import { api } from '../api/client'

const overlay={position:'fixed',inset:0,background:'rgba(0,0,0,.7)',display:'flex',alignItems:'center',justifyContent:'center',zIndex:1000}
const modal={background:'var(--surface)',borderRadius:10,border:'1px solid var(--border)',width:'min(600px,95vw)',maxHeight:'84vh',display:'flex',flexDirection:'column',overflow:'hidden'}
const EMPTY={name:'',entity_type:'person',description:'',plate_number:'',alert_priority:'HIGH'}

export default function WatchlistModal({onClose,testMode=false,testSession=null}){
 const[entries,setEntries]=useState([]),[form,setForm]=useState(EMPTY),[loading,setLoading]=useState(false),[tab,setTab]=useState('list'),[personFile,setPersonFile]=useState(null),[personCheck,setPersonCheck]=useState(null),[checking,setChecking]=useState(false),[error,setError]=useState('')
 useEffect(()=>{load()},[testMode,testSession?.id])
 const load=async()=>{try{setEntries(testMode&&testSession?.id?await api.getTestWatchlist(testSession.id):await api.getWatchlist())}catch(e){setError(e.message)}}
 const change=(field,value)=>{setForm(f=>({...f,[field]:value}));setError('')}
 const choosePerson=async e=>{const file=e.target.files?.[0];e.target.value='';if(!file)return;if(!file.type.startsWith('image/')){setError('Select an image file.');return}setPersonFile(file);setPersonCheck(null);setChecking(true);setError('');try{setPersonCheck(await api.validatePersonPhoto(file,testMode&&testSession?.id?testSession.id:undefined))}catch(err){setError(err.message)}finally{setChecking(false)}}
 const submit=async()=>{
   if(!form.name.trim())return setError('Name is required.')
   if(form.entity_type==='person'){
     if(!personFile)return setError('Upload one reference photo for a person watchlist entry.')
     if(!personCheck?.valid||Number(personCheck.face_count)!==1)return setError('The photo must contain exactly one visible face.')
   }
   setLoading(true);setError('')
   try{
     if(form.entity_type==='person') {if(testMode&&testSession?.id) await api.addTestWatchlistPersonPhoto(testSession.id,form,personFile); else await api.addWatchlistPersonPhoto(form,personFile)}
     else {const payload={...form,plate_number:form.plate_number?.trim()||null};if(testMode&&testSession?.id) await api.addTestWatchlist(testSession.id,payload); else await api.addWatchlist(payload)}
     setForm(EMPTY);setPersonFile(null);setPersonCheck(null);await load();setTab('list')
   }catch(e){setError(e.message)}finally{setLoading(false)}
 }
 const remove=async id=>{if(!confirm('Deactivate this entry?'))return;try{if(testMode&&testSession?.id) await api.removeTestWatchlist(testSession.id,id); else await api.removeWatchlist(id);await load()}catch(e){setError(e.message)}}
 const inp=(field,placeholder,type='text')=><input type={type} placeholder={placeholder} value={form[field]} onChange={e=>change(field,e.target.value)} style={{width:'100%',padding:'8px 10px',borderRadius:6,marginBottom:8,border:'1px solid var(--border)',background:'var(--surface2)',color:'var(--text)',fontSize:13}}/>
 return <div style={overlay} onClick={e=>e.target===e.currentTarget&&onClose()}><div style={modal}>
  <div style={{padding:'14px 18px',borderBottom:'1px solid var(--border)',display:'flex',justifyContent:'space-between',alignItems:'center'}}><span style={{fontWeight:700,fontSize:15}}>{testMode?'Test Watchlist':'Watchlist'}</span><button onClick={onClose} aria-label="Close" style={{background:'none',border:'none',color:'var(--text2)',cursor:'pointer',fontSize:20}}>×</button></div>
  <div style={{display:'flex',borderBottom:'1px solid var(--border)'}}>{[['list','View All'],['add','Add Entry']].map(([t,l])=><button key={t} onClick={()=>{setTab(t);setError('')}} style={{flex:1,padding:'9px 0',border:'none',borderBottom:`2px solid ${tab===t?'var(--accent)':'transparent'}`,background:'transparent',color:tab===t?'var(--accent)':'var(--text2)',cursor:'pointer',fontSize:13}}>{l}</button>)}</div>
  <div style={{flex:1,overflowY:'auto',padding:18}}>
   {tab==='list'&&<><div style={{fontSize:13,color:'var(--text2)',marginBottom:10}}>{entries.length} active entries</div>{entries.map(e=><div key={e.id} style={{padding:'10px 12px',marginBottom:8,borderRadius:8,background:'var(--surface2)',border:'1px solid var(--border)',display:'flex',gap:10,alignItems:'flex-start'}}><div style={{fontSize:20}}>{e.entity_type==='vehicle'?'V':'P'}</div><div style={{flex:1,minWidth:0}}><div style={{fontWeight:600,fontSize:13}}>{e.name}</div>{e.plate_number&&<div style={{fontSize:12,color:'var(--accent)',marginTop:2}}>Plate: {e.plate_number}</div>}{e.entity_type==='person'&&<div style={{fontSize:10,color:'var(--text2)',marginTop:3}}>Face embedding: {e.is_active?'active':'inactive'}</div>}{e.description&&<div style={{fontSize:12,color:'var(--text2)',marginTop:2}}>{e.description}</div>}</div><div style={{display:'flex',flexDirection:'column',alignItems:'flex-end',gap:4}}><span style={{fontSize:10,fontWeight:700,color:e.alert_priority==='HIGH'?'var(--high)':'var(--medium)',background:(e.alert_priority==='HIGH'?'var(--high)':'var(--medium)')+'22',padding:'1px 6px',borderRadius:4}}>{e.alert_priority}</span><button onClick={()=>remove(e.id)} style={{fontSize:11,padding:'2px 8px',borderRadius:4,border:'1px solid var(--border)',background:'transparent',color:'var(--red)',cursor:'pointer'}}>Remove</button></div></div>)}{entries.length===0&&<div style={{textAlign:'center',padding:32,color:'var(--text2)',fontSize:13}}>Watchlist empty</div>}</>}
   {tab==='add'&&<div>
    <label style={{fontSize:12,color:'var(--text2)',display:'block',marginBottom:4}}>Full Name *</label>{inp('name','Person / Vehicle name')}
    <label style={{fontSize:12,color:'var(--text2)',display:'block',marginBottom:4}}>Type</label><select value={form.entity_type} onChange={e=>{change('entity_type',e.target.value);setPersonFile(null);setPersonCheck(null)}} style={{width:'100%',padding:'8px 10px',borderRadius:6,marginBottom:8,border:'1px solid var(--border)',background:'var(--surface2)',color:'var(--text)',fontSize:13}}><option value="person">Person</option><option value="vehicle">Vehicle</option></select>
    {form.entity_type==='person'?<div style={{padding:12,border:'1px dashed var(--accent-border)',borderRadius:8,background:'var(--accent-soft)',marginBottom:8}}><div style={{fontSize:11,color:'var(--text2)',marginBottom:8}}>Upload exactly one clear reference face. The image is validated before the embedding is stored.</div><input id="watchlist-person-photo" type="file" accept="image/*" onChange={choosePerson} style={{display:'none'}}/><label htmlFor="watchlist-person-photo" style={{display:'inline-flex',padding:'8px 11px',borderRadius:7,background:'var(--accent)',color:'#140b04',fontWeight:800,fontSize:11,cursor:'pointer'}}>{personFile?'Replace photo':'Upload photo'}</label>{checking&&<span style={{marginLeft:8,fontSize:10,color:'var(--text2)'}}>Checking…</span>}{personCheck&&<span style={{marginLeft:8,fontSize:10,color:personCheck.valid&&Number(personCheck.face_count)===1?'var(--green)':'var(--red)',fontWeight:700}}>{personCheck.valid?`Face detected · ${personCheck.face_count}`:'No visible face'}</span>}</div>:inp('plate_number','License plate (e.g. GJ03AA1234)')}
    {inp('description','Description / notes')}<label style={{fontSize:12,color:'var(--text2)',display:'block',marginBottom:4}}>Alert Priority</label><select value={form.alert_priority} onChange={e=>change('alert_priority',e.target.value)} style={{width:'100%',padding:'8px 10px',borderRadius:6,marginBottom:12,border:'1px solid var(--border)',background:'var(--surface2)',color:'var(--text)',fontSize:13}}><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select>{error&&<div style={{padding:9,marginBottom:10,borderRadius:7,border:'1px solid rgba(248,113,113,.4)',background:'rgba(248,113,113,.08)',color:'var(--high)',fontSize:11}}>{error}</div>}<button onClick={submit} disabled={loading||checking} style={{width:'100%',padding:'10px',borderRadius:6,border:'none',background:'var(--accent)',color:'#140b04',fontWeight:800,fontSize:14,cursor:'pointer',opacity:loading?.6:1}}>{loading?'Adding…':form.entity_type==='person'?'Add Person to Watchlist':'Add to Watchlist'}</button>
   </div>}
  </div>
 </div></div>
}
