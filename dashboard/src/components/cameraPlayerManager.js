import { useEffect, useState } from 'react'

const MAX_PLAYERS = 6
const KEEP_ALIVE_SLOTS = 2
const OFFSCREEN_DELAY = 1200
const entries = new Map()
const elementToId = new WeakMap()
let observer = null
let pageHidden = typeof document !== 'undefined' && document.visibilityState === 'hidden'
let memoryLimit = MAX_PLAYERS
const keepAliveIds = new Set()

function ensureObserver() {
  if (observer || typeof IntersectionObserver === 'undefined') return
  observer = new IntersectionObserver(records => {
    for (const record of records) {
      const id = elementToId.get(record.target)
      const item = id ? entries.get(id) : null
      if (!item) continue
      item.visible = record.isIntersecting && record.intersectionRatio > 0
      if (item.visible) {
        clearTimeout(item.suspendTimer)
        item.suspendTimer = null
        scheduleBudget()
      } else if (!item.pageSuspended && !keepAliveIds.has(item.id)) {
        clearTimeout(item.suspendTimer)
        item.suspendTimer = setTimeout(() => {
          const current = entries.get(item.id)
          if (current && !current.visible && !current.pageSuspended && !keepAliveIds.has(current.id)) {
            current.setActive(false)
            current.suspended = true
          }
        }, OFFSCREEN_DELAY)
      }
    }
  }, { root: null, rootMargin: '40px 0px', threshold: [0, 0.1] })
}

function distanceFromViewportCenter(item) {
  const r = item.element?.getBoundingClientRect?.()
  if (!r || typeof window === 'undefined') return Number.MAX_SAFE_INTEGER
  return Math.hypot(r.left + r.width / 2 - window.innerWidth / 2, r.top + r.height / 2 - window.innerHeight / 2)
}

let budgetTimer = null
function scheduleBudget() {
  if (budgetTimer) return
  budgetTimer = requestAnimationFrame(() => {
    budgetTimer = null
    recompute(false)
  })
}

function recompute(stagger) {
  if (pageHidden) return
  const eligible = [...entries.values()]
    .filter(item => item.visible && !item.pageSuspended)
    .sort((a, b) => distanceFromViewportCenter(a) - distanceFromViewportCenter(b))
  const wanted = new Set(eligible.slice(0, Math.min(MAX_PLAYERS, memoryLimit)).map(item => item.id))
  eligible.forEach((item, index) => {
    clearTimeout(item.activationTimer)
    if (wanted.has(item.id)) {
      if (item.active) return
      const delay = stagger ? (index < 4 ? 0 : Math.floor((index - 2) / 2) * 500) : 0
      item.activationTimer = setTimeout(() => {
        const current = entries.get(item.id)
        if (current && current.visible && !pageHidden) current.setActive(true)
      }, delay)
    } else {
      item.setActive(false)
    }
  })
  entries.forEach(item => {
    if (!item.visible && !keepAliveIds.has(item.id)) item.setActive(false)
  })
}

function updateKeepAlive() {
  keepAliveIds.clear()
  if (!pageHidden) {
    entries.forEach(item => {
      item.pagePaused = false
    })
    return
  }
  const candidates = [...entries.values()]
    .filter(item => item.visible || item.active)
    .sort((a, b) => distanceFromViewportCenter(a) - distanceFromViewportCenter(b))
    .slice(0, KEEP_ALIVE_SLOTS)
  candidates.forEach(item => {
    keepAliveIds.add(item.id)
    item.pagePaused = true
    item.setActive(true)
  })
}

function onVisibilityChange() {
  pageHidden = document.visibilityState === 'hidden'
  if (pageHidden) {
    entries.forEach(item => {
      item.pageSuspended = item.visible || item.active
      clearTimeout(item.suspendTimer)
    })
    updateKeepAlive()
    entries.forEach(item => {
      if (!keepAliveIds.has(item.id)) item.setActive(false)
    })
  } else {
    keepAliveIds.clear()
    entries.forEach(item => {
      item.pageSuspended = false
      item.pagePaused = false
    })
    recompute(true)
  }
}

if (typeof document !== 'undefined') document.addEventListener('visibilitychange', onVisibilityChange)
if (typeof window !== 'undefined') {
  window.addEventListener('resize', () => recompute(false), { passive: true })
  window.addEventListener('scroll', () => scheduleBudget(), { passive: true, capture: true })
}
if (typeof performance !== 'undefined' && performance.memory) {
  setInterval(() => {
    const ratio = performance.memory.usedJSHeapSize / Math.max(1, performance.memory.jsHeapSizeLimit)
    memoryLimit = ratio > 0.8 ? 4 : MAX_PLAYERS
    recompute(false)
  }, 5000)
}

export function useCameraPlayerSlot(id, elementRef) {
  const [active, setActive] = useState(false)
  const [pagePaused, setPagePaused] = useState(false)

  useEffect(() => {
    ensureObserver()
    const element = elementRef.current
    if (!element) return undefined
    if (!observer) {
      setActive(true)
      return undefined
    }
    const key = String(id)
    const item = {
      id: key,
      element,
      setActive,
      active: false,
      visible: false,
      pageSuspended: false,
      pagePaused: false,
      suspended: false,
      suspendTimer: null,
      activationTimer: null,
    }
    entries.set(key, item)
    elementToId.set(element, key)
    observer.observe(element)
    scheduleBudget()
    return () => {
      clearTimeout(item.suspendTimer)
      clearTimeout(item.activationTimer)
      observer.unobserve(element)
      entries.delete(key)
      keepAliveIds.delete(key)
      setActive(false)
      setPagePaused(false)
    }
  }, [id, elementRef])

  useEffect(() => {
    const item = entries.get(String(id))
    if (!item) return undefined
    item.active = active
    const syncPaused = () => setPagePaused(Boolean(item.pagePaused && keepAliveIds.has(String(id))))
    syncPaused()
    const timer = setInterval(syncPaused, 250)
    return () => clearInterval(timer)
  }, [id, active])

  return { active, pagePaused }
}
