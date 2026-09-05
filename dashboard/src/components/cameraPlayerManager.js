import { useEffect, useState } from 'react'

const MAX_PLAYERS=12
const OFFSCREEN_DELAY=5000
const entries=new Map()
const elementToId=new WeakMap()
let observer=null
let pageHidden=typeof document!=='undefined' && document.visibilityState==='hidden'
let memoryLimit=MAX_PLAYERS

function ensureObserver(){
  if(observer || typeof IntersectionObserver==='undefined') return
  observer=new IntersectionObserver(records=>{
    for(const record of records){
      const id=elementToId.get(record.target), item=id?entries.get(id):null
      if(!item) continue
      item.visible=record.isIntersecting && record.intersectionRatio>0
      if(item.visible){clearTimeout(item.suspendTimer);item.suspendTimer=null;scheduleBudget()}
      else if(!item.pageSuspended){clearTimeout(item.suspendTimer);item.suspendTimer=setTimeout(()=>{const current=entries.get(item.id);if(current&&!current.visible&&!current.pageSuspended){current.setActive(false);current.suspended=true}},OFFSCREEN_DELAY)}
    }
  },{root:null,rootMargin:'200px 0px',threshold:[0,0.1]})
}
function distanceFromViewportCenter(item){const r=item.element?.getBoundingClientRect?.();if(!r||typeof window==='undefined')return Number.MAX_SAFE_INTEGER;return Math.hypot(r.left+r.width/2-window.innerWidth/2,r.top+r.height/2-window.innerHeight/2)}
let budgetTimer=null
function scheduleBudget(){clearTimeout(budgetTimer);budgetTimer=setTimeout(()=>recompute(false),0)}
function recompute(stagger){if(pageHidden)return;const eligible=[...entries.values()].filter(item=>item.visible&&!item.pageSuspended).sort((a,b)=>distanceFromViewportCenter(a)-distanceFromViewportCenter(b));const wanted=new Set(eligible.slice(0,Math.min(MAX_PLAYERS,memoryLimit)).map(item=>item.id));eligible.forEach((item,index)=>{clearTimeout(item.activationTimer);if(wanted.has(item.id)){if(item.active)return;const delay=stagger?(index<4?0:Math.floor((index-2)/2)*500):0;item.activationTimer=setTimeout(()=>{const current=entries.get(item.id);if(current&&current.visible&&!pageHidden)current.setActive(true)},delay)}else item.setActive(false)});entries.forEach(item=>{if(!item.visible)item.setActive(false)})}
function onVisibilityChange(){pageHidden=document.visibilityState==='hidden';if(pageHidden){entries.forEach(item=>{item.pageSuspended=item.visible||item.active;clearTimeout(item.suspendTimer);item.setActive(false)})}else{entries.forEach(item=>{if(item.pageSuspended)item.pageSuspended=false});recompute(true)}}
if(typeof document!=='undefined')document.addEventListener('visibilitychange',onVisibilityChange)
if(typeof window!=='undefined'){window.addEventListener('resize',()=>recompute(false),{passive:true});window.addEventListener('scroll',()=>scheduleBudget(),{passive:true})}
if(typeof performance!=='undefined'&&performance.memory)setInterval(()=>{const ratio=performance.memory.usedJSHeapSize/Math.max(1,performance.memory.jsHeapSizeLimit);memoryLimit=ratio>0.8?8:MAX_PLAYERS;if(memoryLimit<MAX_PLAYERS)recompute(false)},5000)

export function useCameraPlayerSlot(id,elementRef){const[active,setActive]=useState(false);useEffect(()=>{ensureObserver();const element=elementRef.current;if(!element)return undefined;if(!observer){setActive(true);return undefined}const key=String(id);const item={id:key,element,setActive,active:false,visible:false,pageSuspended:false,suspended:false,suspendTimer:null,activationTimer:null};entries.set(key,item);elementToId.set(element,key);observer.observe(element);scheduleBudget();return()=>{clearTimeout(item.suspendTimer);clearTimeout(item.activationTimer);observer.unobserve(element);entries.delete(key);setActive(false)}},[id,elementRef]);useEffect(()=>{const item=entries.get(String(id));if(item)item.active=active},[id,active]);return active}
