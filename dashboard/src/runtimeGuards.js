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

function browserSessionToken() {
  return localStorage.getItem('sentinel.jwt') || localStorage.getItem('sentinel_token') || null
}

function isCctvRequest(url) {
  try {
    const parsed = new URL(url, window.location.href)
    return parsed.origin === window.location.origin && parsed.pathname.startsWith('/api/cctv/')
  } catch {
    return false
  }
}

function installCctvXHRAuth() {
  const XHR = window.XMLHttpRequest
  if (!XHR || XHR.prototype.__sentinelCctvAuthInstalled) return

  const originalOpen = XHR.prototype.open
  const originalSend = XHR.prototype.send
  const originalSetRequestHeader = XHR.prototype.setRequestHeader

  XHR.prototype.open = function sentinelOpen(method, url, ...rest) {
    this.__sentinelCctvUrl = String(url || '')
    this.__sentinelCctvMethod = String(method || 'GET').toUpperCase()
    return originalOpen.call(this, method, url, ...rest)
  }

  XHR.prototype.send = function sentinelSend(body) {
    const method = this.__sentinelCctvMethod || 'GET'
    const url = this.__sentinelCctvUrl || ''
    const token = browserSessionToken()
    if (method === 'GET' && token && isCctvRequest(url) && !/[?&]access_token=/.test(url)) {
      try {
        originalSetRequestHeader.call(this, 'Authorization', `Bearer ${token}`)
      } catch {
        // Some browser/runtime implementations can reject header mutation after open.
      }
    }
    return originalSend.call(this, body)
  }

  XHR.prototype.__sentinelCctvAuthInstalled = true
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
  installCctvXHRAuth()
  installMetadataGuard()
}
