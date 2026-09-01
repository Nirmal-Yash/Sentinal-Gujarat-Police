import React from 'react'

const TYPE_LABELS = {
  anomaly_crowd_formation: 'Crowd Formation',
  anomaly_running_crowd: 'Running Crowd',
  anomaly_abandoned_object: 'Abandoned Object',
  anpr_watchlist: 'ANPR Watchlist',
  face_watchlist: 'Face Watchlist',
}

export default function AlertTypeBadge({ type = 'alert', compact = false }) {
  const key = String(type || 'alert').toLowerCase()
  const label = TYPE_LABELS[key] || key.replace(/[_-]+/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  return <span aria-label={`Alert type ${label}`} style={{ display: 'inline-flex', alignItems: 'center', minHeight: compact ? 20 : 22, padding: compact ? '0 6px' : '0 8px', borderRadius: 6, background: 'rgba(249,115,22,.07)', border: '1px solid rgba(249,115,22,.22)', color: 'var(--accent-strong)', fontSize: compact ? 8 : 9, fontWeight: 800 }}>{label}</span>
}

export { TYPE_LABELS }
