const ALERT_TYPE_QUERY_MAP = {
  WATCHLIST_HIT: 'watchlist',
  PLATE_SIGHTING: 'plate',
  PERSON_MATCH: 'person',
  CROWD_ANOMALY: 'crowd',
  RUNNING_CROWD: 'running',
}

export function mapAlertTypeFilter(alertType) {
  if (!alertType || alertType === 'ALL') return ''
  return ALERT_TYPE_QUERY_MAP[alertType] || alertType
}

export function canonicalAlertType(type) {
  const raw = String(type || '').toLowerCase()
  if (raw.includes('watchlist')) return 'WATCHLIST_HIT'
  if (raw.includes('plate') || raw.includes('anpr')) return 'PLATE_SIGHTING'
  if (raw.includes('person') || raw.includes('face') || raw.includes('cross_camera')) return 'PERSON_MATCH'
  if (raw.includes('running')) return 'RUNNING_CROWD'
  if (raw.includes('crowd')) return 'CROWD_ANOMALY'
  return String(type || '').toUpperCase()
}

export function alertTimestamp(alert) {
  const raw = alert?.event_at ?? alert?.created_at ?? alert?.detected_at
  if (raw == null || raw === '') return 0
  if (typeof raw === 'number') return raw < 1e12 ? raw * 1000 : raw
  const parsed = Date.parse(raw)
  return Number.isFinite(parsed) ? parsed : 0
}

export function resolveAlertDateRange(dateFilter) {
  if (!dateFilter || dateFilter.preset === 'ALL') return { from: '', to: '' }
  if (dateFilter.preset === 'CUSTOM') {
    return {
      from: dateFilter.from ? `${dateFilter.from}T00:00:00.000Z` : '',
      to: dateFilter.to ? `${dateFilter.to}T23:59:59.999Z` : '',
    }
  }
  const now = new Date()
  const hours = dateFilter.preset === '1H'
    ? 1
    : dateFilter.preset === '24H'
      ? 24
      : dateFilter.preset === '7D'
        ? 168
        : 720
  return {
    from: new Date(now.getTime() - hours * 3600000).toISOString(),
    to: now.toISOString(),
  }
}

export function buildAlertQueryParams(filters, { limit = 300 } = {}) {
  const dateRange = resolveAlertDateRange(filters.date)
  return {
    limit,
    ...(filters.priority !== 'ALL' ? { priority: filters.priority } : {}),
    ...(filters.status !== 'ALL' ? { status: filters.status } : {}),
    ...(filters.alertType !== 'ALL' ? { alert_type: mapAlertTypeFilter(filters.alertType) } : {}),
    ...(filters.camera ? { camera: filters.camera } : {}),
    ...(filters.plate ? { plate: filters.plate } : {}),
    ...(dateRange.from ? { from: dateRange.from } : {}),
    ...(dateRange.to ? { to: dateRange.to } : {}),
  }
}
