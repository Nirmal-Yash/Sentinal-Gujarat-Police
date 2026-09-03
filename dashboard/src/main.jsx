import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { applyTheme, resolveInitialTheme } from './hooks/useTheme.js'
import './styles.css'
import './interactionEffects.css'
import './theme.css'
import App from './App.jsx'
import ToastHost from './components/alerts/ToastHost.jsx'
import { installSentinelRuntimeGuards } from './runtimeGuards.js'
import { installSmoothLeafletNavigation } from './mapNavigation.js'

// Apply the persisted theme before React paints to avoid an opposite-theme flash.
applyTheme(resolveInitialTheme(), { announce: false })

// Metadata is intentionally always expanded; the dialog exposes only its close action.
const metadataStyle = document.createElement('style')
metadataStyle.textContent = 'section[role="dialog"][aria-label*="metadata"] header > button[aria-label="Collapse metadata"],section[role="dialog"][aria-label*="metadata"] header > button[aria-label="Expand metadata"]{display:none!important}'
document.head.appendChild(metadataStyle)

installSentinelRuntimeGuards()
installSmoothLeafletNavigation()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
    <ToastHost />
  </StrictMode>,
)
