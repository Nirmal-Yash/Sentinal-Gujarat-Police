import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './styles.css'
import { installSentinelRuntimeGuards } from './runtimeGuards.js'

// Metadata is intentionally always expanded; the dialog exposes only its close action.
const metadataStyle = document.createElement('style')
metadataStyle.textContent = 'section[role="dialog"][aria-label*="metadata"] header > button:first-of-type{display:none!important}'
document.head.appendChild(metadataStyle)

installSentinelRuntimeGuards()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
