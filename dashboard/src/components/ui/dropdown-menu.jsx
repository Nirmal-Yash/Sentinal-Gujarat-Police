import React, { createContext, useContext, useEffect, useRef, useState } from 'react'

const DropdownContext = createContext(null)
export function DropdownMenu({ children }) {
  const [open,setOpen]=useState(false)
  const root=useRef(null)
  useEffect(()=>{const close=e=>{if(root.current&&!root.current.contains(e.target))setOpen(false)};document.addEventListener('mousedown',close);return()=>document.removeEventListener('mousedown',close)},[])
  return <DropdownContext.Provider value={{open,setOpen}}><div ref={root} className="ui-dropdown">{children}</div></DropdownContext.Provider>
}
export function DropdownMenuTrigger({ children, asChild=false }) {
  const { open,setOpen }=useContext(DropdownContext)
  if(asChild) return React.cloneElement(children,{onClick:e=>{children.props.onClick?.(e);setOpen(!open)},'aria-expanded':open})
  return <button type="button" onClick={()=>setOpen(!open)} aria-expanded={open}>{children}</button>
}
export function DropdownMenuContent({ children, align='end' }) {
  const { open }=useContext(DropdownContext)
  if(!open)return null
  return <div className={`ui-dropdown-content ui-dropdown-align-${align}`}>{children}</div>
}
export function DropdownMenuItem({ children, onSelect, disabled=false }) {
  const { setOpen }=useContext(DropdownContext)
  return <button type="button" disabled={disabled} className="ui-dropdown-item" onClick={()=>{if(!disabled){onSelect?.();setOpen(false)}}}>{children}</button>
}
export function DropdownMenuLabel({ children }) { return <div className="ui-dropdown-label">{children}</div> }
export function DropdownMenuSeparator(){return <div className="ui-dropdown-separator"/>}
