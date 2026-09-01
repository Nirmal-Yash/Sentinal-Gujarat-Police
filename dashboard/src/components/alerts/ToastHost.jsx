import React, { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

export default function ToastHost() {
  const [items, setItems] = useState([])
  useEffect(() => {
    const onToast = event => {
      const item = { id: `${Date.now()}-${Math.random()}`, ...(event.detail || {}) }
      setItems(current => [...current, item].slice(-4))
      window.setTimeout(() => setItems(current => current.filter(x => x.id !== item.id)), 3200)
    }
    window.addEventListener('sentinel:toast', onToast)
    return () => window.removeEventListener('sentinel:toast', onToast)
  }, [])
  return <div style={{ position: 'fixed', right: 18, bottom: 18, zIndex: 5000, display: 'flex', flexDirection: 'column', gap: 8, pointerEvents: 'none' }}>
    <AnimatePresence initial={false}>
      {items.map(item => <motion.div key={item.id} initial={{ opacity: 0, y: 10, scale: .98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: .18 }} style={{ minWidth: 220, maxWidth: 360, padding: '10px 12px', borderRadius: 9, border: `1px solid ${item.type === 'error' ? 'rgba(248,113,113,.45)' : item.type === 'success' ? 'rgba(74,222,128,.4)' : 'var(--border)'}`, background: '#0b0907', boxShadow: '0 15px 35px rgba(0,0,0,.55)', color: 'var(--text)', fontSize: 11, fontWeight: 700 }}>{item.message}</motion.div>)}
    </AnimatePresence>
  </div>
}
