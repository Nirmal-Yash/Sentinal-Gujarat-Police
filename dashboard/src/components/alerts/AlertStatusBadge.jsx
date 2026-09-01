import React from 'react'

const STATUS_STYLES = {
  NEW: { label: 'New', tone: '#fb923c', bg: 'rgba(251,146,60,.12)', border: 'rgba(251,146,60,.35)' },
  ACKNOWLEDGED: { label: 'Acknowledged', tone: '#60a5fa', bg: 'rgba(96,165,250,.12)', border: 'rgba(96,165,250,.35)' },
  INVESTIGATING: { label: 'Investigating', tone: '#c084fc', bg: 'rgba(192,132,252,.12)', border: 'rgba(192,132,252,.35)' },
  RESOLVED: { label: 'Resolved', tone: '#4ade80', bg: 'rgba(74,222,128,.12)', border: 'rgba(74,222,128,.35)' },
  CLOSED: { label: 'Closed', tone: '#94a3b8', bg: 'rgba(148,163,184,.12)', border: 'rgba(148,163,184,.3)' },
}

export default function AlertStatusBadge({ status = 'NEW' }) {
  const key = String(status || 'NEW').toUpperCase()
  const style = STATUS_STYLES[key] || STATUS_STYLES.NEW
  return <span aria-label={`Status ${style.label}`} style={{ display: 'inline-flex', alignItems: 'center', minHeight: 22, padding: '0 7px', borderRadius: 999, background: style.bg, border: `1px solid ${style.border}`, color: style.tone, fontSize: 9, fontWeight: 850, letterSpacing: .2 }}>{style.label}</span>
}

export { STATUS_STYLES }
