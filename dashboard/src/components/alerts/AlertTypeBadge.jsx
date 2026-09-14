import React from 'react'

const TYPE_LABELS = {
  WATCHLIST_HIT: 'Watchlist Hit',
  PLATE_SIGHTING: 'Plate Sighting',
  PERSON_MATCH: 'Person Match',
  CROWD_ANOMALY: 'Crowd Anomaly',
  RUNNING_CROWD: 'Running Crowd',
  watchlist_match: 'Watchlist Hit',
  anomaly_crowd_formation: 'Crowd Formation',
  anomaly_running_crowd: 'Running Crowd',
  anomaly_abandoned_object: 'Abandoned Object',
  anpr_watchlist: 'ANPR Watchlist',
  face_watchlist: 'Face Watchlist',
}

export default function AlertTypeBadge({ type = 'alert', compact = false }) {
  const raw = String(type || 'alert')
  const key = raw.toLowerCase()
  const label = TYPE_LABELS[raw] || TYPE_LABELS[key] || raw.replace(/[_-]+/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  return (
    <span
      aria-label={`Alert type ${label}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        minHeight: compact ? 20 : 22,
        padding: compact ? '0 6px' : '0 8px',
        borderRadius: 6,
        background: 'var(--accent-soft)',
        border: '1px solid var(--accent-border)',
        color: 'var(--accent-strong)',
        fontSize: compact ? 8 : 9,
        fontWeight: 800,
      }}
    >
      {label}
    </span>
  )
}

export { TYPE_LABELS }
