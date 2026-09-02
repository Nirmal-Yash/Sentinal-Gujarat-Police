import { useEffect, useState } from 'react'

const STORAGE_KEY = 'sentinel_theme'
const THEME_EVENT = 'sentinel:theme-change'
const VALID = new Set(['light', 'dark'])
const MEDIA_QUERY = '(prefers-color-scheme: dark)'

export function resolveInitialTheme() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (VALID.has(stored)) return stored
  } catch {}
  return window.matchMedia?.(MEDIA_QUERY).matches ? 'dark' : 'light'
}

export function applyTheme(theme, { persist = true, announce = true } = {}) {
  const next = VALID.has(theme) ? theme : 'dark'
  const root = document.documentElement
  root.dataset.theme = next
  root.classList.toggle('dark', next === 'dark')
  root.style.colorScheme = next

  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.setAttribute('content', next === 'dark' ? '#0b0b0a' : '#f4f6f8')

  if (persist) {
    try { localStorage.setItem(STORAGE_KEY, next) } catch {}
  }
  if (announce) {
    window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: next }))
  }
  return next
}

// Apply before React paints so the first frame, authenticated shell and login screen
// all start in the same persisted theme without a flash to the opposite mode.
const INITIAL_THEME = resolveInitialTheme()
applyTheme(INITIAL_THEME, { announce: false })

export function useTheme() {
  const [theme, setTheme] = useState(() => INITIAL_THEME)

  useEffect(() => {
    const syncTheme = next => {
      if (!VALID.has(next)) return
      setTheme(current => current === next ? current : next)
      applyTheme(next, { persist: true, announce: false })
    }

    const onStorage = event => {
      if (event.key === STORAGE_KEY && VALID.has(event.newValue)) syncTheme(event.newValue)
    }

    const onThemeChange = event => {
      if (VALID.has(event.detail)) syncTheme(event.detail)
    }

    window.addEventListener('storage', onStorage)
    window.addEventListener(THEME_EVENT, onThemeChange)
    return () => {
      window.removeEventListener('storage', onStorage)
      window.removeEventListener(THEME_EVENT, onThemeChange)
    }
  }, [])

  const toggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    const update = () => {
      applyTheme(next, { persist: true, announce: true })
      setTheme(next)
    }

    if (typeof document.startViewTransition === 'function' && !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      try {
        document.startViewTransition(update)
        return
      } catch {}
    }
    update()
  }

  return { theme, toggle }
}
