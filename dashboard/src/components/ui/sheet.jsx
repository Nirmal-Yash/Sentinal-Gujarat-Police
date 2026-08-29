import React, { useEffect } from 'react'

export function Sheet({ open=false, onOpenChange, children }) {
  useEffect(() => {
    if (!open) return
    const onKey = event => { if (event.key === 'Escape') onOpenChange?.(false) }
    document.addEventListener('keydown', onKey)
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = previous }
  }, [open, onOpenChange])
  if (!open) return null
  return <div className="ui-sheet-overlay" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) onOpenChange?.(false) }}>{children}</div>
}
export function SheetContent({ children, side='right', className='' }) {
  return <aside className={`ui-sheet-content ui-sheet-${side} ${className}`.trim()} role="dialog" aria-modal="true">{children}</aside>
}
export function SheetHeader({ children }) { return <header className="ui-sheet-header">{children}</header> }
export function SheetTitle({ children }) { return <h2 className="ui-sheet-title">{children}</h2> }
export function SheetDescription({ children }) { return <p className="ui-sheet-description">{children}</p> }
export function SheetClose({ onClose, children }) { return <button type="button" className="ui-sheet-close" onClick={onClose} aria-label="Close panel" title="Close panel">{children || '×'}</button> }
export function SheetBody({ children }) { return <div className="ui-sheet-body">{children}</div> }
