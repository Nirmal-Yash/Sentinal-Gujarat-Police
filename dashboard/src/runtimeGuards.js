const SNAPSHOT_CACHE_TTL_MS = 15000
const SNAPSHOT_CACHE = new Map()
const SNAPSHOT_INFLIGHT = new Map()
const INSTALL_KEY = '__sentinelRuntimeGuardsInstalled'

function snapshotKey(input) {
  try {
    const url = new URL(typeof input === 'string' ? input : input.url, window.location.href)
    if (!/^\/api\/cameras\/[^/]+\/snapshot$/.test(url.pathname)) return null
    return url.pathname
  } catch {
    return null
  }
}

function cloneHeaders(headers) {
  const copy = new Headers()
  for (const [key, value] of headers.entries()) copy.set(key, value)
  return copy
}

async function readSnapshotResult(response) {
  const body = await response.arrayBuffer()
  return {
    body,
    headers: cloneHeaders(response.headers),
    status: response.status,
    statusText: response.statusText,
  }
}

function responseFromResult(result) {
  return new Response(result.body.slice(0), {
    status: result.status,
    statusText: result.statusText,
    headers: result.headers,
  })
}

function installSnapshotGuard() {
  const originalFetch = window.fetch.bind(window)

  window.fetch = async function sentinelFetch(input, init) {
    const key = snapshotKey(input)
    if (!key || String(init?.method || 'GET').toUpperCase() !== 'GET') {
      return originalFetch(input, init)
    }

    const now = Date.now()
    const cached = SNAPSHOT_CACHE.get(key)
    if (cached && now - cached.timestamp < SNAPSHOT_CACHE_TTL_MS) {
      return responseFromResult(cached.result)
    }

    const existing = SNAPSHOT_INFLIGHT.get(key)
    if (existing) {
      return responseFromResult(await existing)
    }

    const request = originalFetch(input, init)
      .then(response => readSnapshotResult(response))
      .then(result => {
        // Cache both successful snapshots and short-lived failures. This prevents
        // an unavailable/unauthenticated camera from generating a request every
        // few seconds while the player is still waiting for HLS.
        SNAPSHOT_CACHE.set(key, { timestamp: Date.now(), result })
        return result
      })
      .finally(() => SNAPSHOT_INFLIGHT.delete(key))

    SNAPSHOT_INFLIGHT.set(key, request)
    return responseFromResult(await request)
  }
}

function installMetadataGuard() {
  const hideCollapse = () => {
    document
      .querySelectorAll('button[aria-label="Collapse metadata"], button[aria-label="Expand metadata"]')
      .forEach(button => button.remove())
  }

  hideCollapse()
  const observer = new MutationObserver(hideCollapse)
  observer.observe(document.body, { childList: true, subtree: true })
  return () => observer.disconnect()
}

export function installSentinelRuntimeGuards() {
  if (window[INSTALL_KEY]) return
  window[INSTALL_KEY] = true
  installSnapshotGuard()
  installMetadataGuard()
}
