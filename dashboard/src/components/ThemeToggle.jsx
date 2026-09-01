import { useTheme } from '../hooks/useTheme'

const Sun=()=> <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>
const Moon=()=> <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M20.5 15.2A8.5 8.5 0 0 1 8.8 3.5 8.5 8.5 0 1 0 20.5 15.2Z"/></svg>

export default function ThemeToggle(){
  const {theme,toggle}=useTheme()
  const next=theme==='dark'?'light':'dark'
  return <button type="button" className="ui-icon-button sentinel-theme-toggle" onClick={toggle} title={`Switch to ${next} theme`} aria-label={`Switch to ${next} theme`}>{theme==='dark'?<Sun/>:<Moon/>}</button>
}
