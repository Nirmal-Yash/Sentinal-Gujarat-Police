import React, { useMemo } from 'react'

const PRESETS = [
  ['ALL', 'All time'],
  ['1H', 'Last hour'],
  ['24H', 'Last 24 hours'],
  ['7D', 'Last 7 days'],
  ['30D', 'Last 30 days'],
  ['CUSTOM', 'Custom'],
]

export default function AlertDateFilter({ value, onChange }) {
  const custom = value?.preset === 'CUSTOM'
  const range = useMemo(() => {
    if (value?.preset === 'ALL' || !value?.preset) return { from: '', to: '' }
    if (value.preset === 'CUSTOM') return { from: value.from || '', to: value.to || '' }
    const hours = value.preset === '1H' ? 1 : value.preset === '24H' ? 24 : value.preset === '7D' ? 168 : 720
    const now = new Date()
    const from = new Date(now.getTime() - hours * 3600000)
    return { from: from.toISOString().slice(0, 10), to: now.toISOString().slice(0, 10) }
  }, [value])

  return <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
    <select aria-label="Alert date range" value={value?.preset || 'ALL'} onChange={e => onChange?.({ preset: e.target.value, from: '', to: '' })} style={selectStyle}>
      {PRESETS.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
    </select>
    {custom && <>
      <input aria-label="Alert start date" type="date" value={range.from} onChange={e => onChange?.({ preset: 'CUSTOM', from: e.target.value, to: range.to })} style={selectStyle} />
      <span style={{ color: 'var(--muted)', fontSize: 10 }}>to</span>
      <input aria-label="Alert end date" type="date" value={range.to} onChange={e => onChange?.({ preset: 'CUSTOM', from: range.from, to: e.target.value })} style={selectStyle} />
    </>}
  </div>
}

export { PRESETS }

const selectStyle = { minHeight: 34, padding: '0 9px', border: '1px solid var(--border)', borderRadius: 7, background: 'var(--surface2)', color: 'var(--text)', fontSize: 10, outline: 'none' }
