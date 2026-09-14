export function sightingTimestamp(sighting) {
  const raw = sighting?.timestamp ?? sighting?.event_at ?? sighting?.created_at ?? sighting?.source_timestamp
  if (raw == null || raw === '') return 0
  if (typeof raw === 'number') return raw < 1e12 ? raw * 1000 : raw
  const parsed = Date.parse(raw)
  return Number.isFinite(parsed) ? parsed : 0
}

export function sortSightingsChronologically(sightings = []) {
  return [...sightings].sort((a, b) => {
    const delta = sightingTimestamp(a) - sightingTimestamp(b)
    if (delta !== 0) return delta
    const streamA = Number(a?.stream_id ?? a?.sequence_no ?? 0)
    const streamB = Number(b?.stream_id ?? b?.sequence_no ?? 0)
    return streamA - streamB
  })
}
