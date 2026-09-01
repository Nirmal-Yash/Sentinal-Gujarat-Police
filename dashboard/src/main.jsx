import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import ToastHost from './components/alerts/ToastHost.jsx'
import './styles.css'
import { installSentinelRuntimeGuards } from './runtimeGuards.js'
import { installSmoothLeafletNavigation } from './mapNavigation.js'

// Metadata is intentionally always expanded; the dialog exposes only its close action.
const metadataStyle = document.createElement('style')
metadataStyle.textContent = 'section[role="dialog"][aria-label*="metadata"] header > button:first-of-type{display:none!important}'
document.head.appendChild(metadataStyle)

installSentinelRuntimeGuards()
installSmoothLeafletNavigation()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
    <ToastHost />
  </StrictMode>,
)
