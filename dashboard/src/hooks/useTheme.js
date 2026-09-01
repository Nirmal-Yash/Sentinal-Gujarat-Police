import { useEffect, useState } from 'react'

const STORAGE_KEY = 'sentinel_theme'
const THEME_EVENT = 'sentinel:theme-change'
const resolveInitial = () => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark') return stored
  } catch {}
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function useTheme() {
  const [theme, setTheme] = useState(resolveInitial)

  useEffect(() => {
    const syncTheme = next => {
      if (next === 'light' || next === 'dark') setTheme(next)
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

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem(STORAGE_KEY, theme) } catch {}
    window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: theme }))
  }, [theme])

  const toggle = () => setTheme(value => value === 'dark' ? 'light' : 'dark')
  return { theme, toggle }
}
