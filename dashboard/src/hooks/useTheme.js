import { useEffect, useState } from 'react'

const STORAGE_KEY = 'sentinel_theme'
const THEME_EVENT = 'sentinel:theme-change'
const VALID = new Set(['light', 'dark'])

const resolveInitial = () => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (VALID.has(stored)) return stored
  } catch {}
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(theme) {
  document.documentElement.classList.toggle('dark', theme === 'dark')
  document.documentElement.dataset.theme = theme
  try { localStorage.setItem(STORAGE_KEY, theme) } catch {}
  window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: theme }))
}

export function useTheme() {
  const [theme, setTheme] = useState(resolveInitial)

  useEffect(() => {
    const syncTheme = next => {
      if (!VALID.has(next)) return
      setTheme(next)
      applyTheme(next)
    }
    const onStorage = event => {
      if (event.key === STORAGE_KEY) syncTheme(event.newValue)
    }
    const onThemeChange = event => syncTheme(event.detail)
    window.addEventListener('storage', onStorage)
    window.addEventListener(THEME_EVENT, onThemeChange)
    return () => {
      window.removeEventListener('storage', onStorage)
      window.removeEventListener(THEME_EVENT, onThemeChange)
    }
  }, [])

  useEffect(() => applyTheme(theme), [theme])

  const toggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    const update = () => setTheme(next)
    if (typeof document.startViewTransition === 'function') {
      try {
        document.startViewTransition(update)
        return
      } catch {}
    }
    update()
  }

  return { theme, toggle }
}
