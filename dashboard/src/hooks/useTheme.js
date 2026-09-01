import { useEffect, useState } from 'react'

const STORAGE_KEY = 'sentinel_theme'
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
    document.documentElement.classList.toggle('dark', theme === 'dark')
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem(STORAGE_KEY, theme) } catch {}
  }, [theme])
  const toggle = () => setTheme(value => value === 'dark' ? 'light' : 'dark')
  return { theme, toggle }
}
