import React from 'react'

const STATUS_STYLES = {
  NEW: { label: 'New', tone: '#FFB300', bg: 'rgba(255,179,0,.12)', border: 'rgba(255,179,0,.35)' },
  ACKNOWLEDGED: { label: 'Acknowledged', tone: '#00E5FF', bg: 'rgba(0,229,255,.12)', border: 'rgba(0,229,255,.35)' },
  INVESTIGATING: { label: 'Investigating', tone: '#A78BFA', bg: 'rgba(167,139,250,.12)', border: 'rgba(167,139,250,.35)' },
  RESOLVED: { label: 'Resolved', tone: '#34C759', bg: 'rgba(52,199,89,.12)', border: 'rgba(52,199,89,.35)' },
  CLOSED: { label: 'Closed', tone: '#8A94A6', bg: 'rgba(138,148,166,.12)', border: 'rgba(138,148,166,.3)' },
}

export default function AlertStatusBadge({ status = 'NEW' }) {
  const key = String(status || 'NEW').toUpperCase()
  const style = STATUS_STYLES[key] || STATUS_STYLES.NEW
  return <span aria-label={`Status ${style.label}`} style={{ display: 'inline-flex', alignItems: 'center', minHeight: 22, padding: '0 7px', borderRadius: 999, background: style.bg, border: `1px solid ${style.border}`, color: style.tone, fontSize: 9, fontWeight: 850, letterSpacing: .2 }}>{style.label}</span>
}

export { STATUS_STYLES }
