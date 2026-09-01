const SNAPSHOT_CACHE_TTL_MS = 15000
const SNAPSHOT_CACHE = new Map()
const SNAPSHOT_INFLIGHT = new Map()
const SNAPSHOT_TOKEN_CACHE = new Map()
const TEST_SESSION_KEY = 'sentinel.test.session.v1'
const INSTALL_KEY = '__sentinelRuntimeGuardsInstalled'

function isTestSessionActive() {
  try { return Boolean(sessionStorage.getItem(TEST_SESSION_KEY)) } catch { return false }
}

function snapshotKey(input) {
  try {
    const url = new URL(typeof input === 'string' ? input : input.url, window.location.href)
    if (!/^\/api\/cameras\/[^/]+\/snapshot$/.test(url.pathname)) return null
    return url.pathname
  } catch { return null }
}

function cloneHeaders(headers) { const copy = new Headers(); for (const [key, value] of headers.entries()) copy.set(key, value); return copy }
async function readSnapshotResult(response) { return { body: await response.arrayBuffer(), headers: cloneHeaders(response.headers), status: response.status, statusText: response.statusText } }
function responseFromResult(result) { return new Response(result.body.slice(0), { status: result.status, statusText: result.statusText, headers: result.headers }) }
function browserSessionToken() { return localStorage.getItem('sentinel.jwt') || localStorage.getItem('sentinel_token') || sessionStorage.getItem('sentinel.jwt') || null }
function isCctvRequest(url) { try { const parsed = new URL(url, window.location.href); return parsed.origin === window.location.origin && parsed.pathname.startsWith('/api/cctv/') } catch { return false } }

async function ensureSnapshotToken(key, originalFetch) {
  const cached = SNAPSHOT_TOKEN_CACHE.get(key)
  if (cached && cached.expiresAt > Date.now() + 5000) return cached.token
  const pendingKey = `${key}:pending`
  if (SNAPSHOT_TOKEN_CACHE.has(pendingKey)) return SNAPSHOT_TOKEN_CACHE.get(pendingKey)
  const match = key.match(/^\/api\/cameras\/([^/]+)\/snapshot$/)
  if (!match) return null
  const sessionToken = browserSessionToken()
  if (!sessionToken) return null
  const request = originalFetch(`/api/cameras/${match[1]}/snapshot-token`, { headers: { Authorization: `Bearer ${sessionToken}` } })
    .then(async response => { if (!response.ok) return null; const payload = await response.json(); if (!payload?.token) return null; SNAPSHOT_TOKEN_CACHE.set(key, { token: payload.token, expiresAt: Date.now() + Math.max(30000, Number(payload.expires_in || 120) * 1000) }); return payload.token })
    .catch(() => null)
    .finally(() => SNAPSHOT_TOKEN_CACHE.delete(pendingKey))
  SNAPSHOT_TOKEN_CACHE.set(pendingKey, request)
  return request
}

function installSnapshotGuard() {
  const originalFetch = window.fetch.bind(window)
  window.fetch = async function sentinelFetch(input, init) {
    const key = snapshotKey(input)
    if (!key || String(init?.method || 'GET').toUpperCase() !== 'GET') return originalFetch(input, init)
    if (isTestSessionActive()) return new Response(null, { status: 204 })
    const url = new URL(typeof input === 'string' ? input : input.url, window.location.href)
    if (!url.searchParams.has('access_token')) {
      const token = await ensureSnapshotToken(key, originalFetch)
      if (token) url.searchParams.set('access_token', token)
      input = new Request(url.toString(), input instanceof Request ? input : undefined)
    }
    const now = Date.now()
    const cached = SNAPSHOT_CACHE.get(key)
    if (cached && now - cached.timestamp < SNAPSHOT_CACHE_TTL_MS) return responseFromResult(cached.result)
    const existing = SNAPSHOT_INFLIGHT.get(key)
    if (existing) return responseFromResult(await existing)
    const request = originalFetch(input, init).then(readSnapshotResult).then(result => { SNAPSHOT_CACHE.set(key, { timestamp: Date.now(), result }); return result }).finally(() => SNAPSHOT_INFLIGHT.delete(key))
    SNAPSHOT_INFLIGHT.set(key, request)
    return responseFromResult(await request)
  }
}

function installCctvXHRAuth() {
  const XHR = window.XMLHttpRequest
  if (!XHR || XHR.prototype.__sentinelCctvAuthInstalled) return
  const originalOpen = XHR.prototype.open
  const originalSend = XHR.prototype.send
  const originalSetRequestHeader = XHR.prototype.setRequestHeader
  XHR.prototype.open = function sentinelOpen(method, url, ...rest) { this.__sentinelCctvUrl = String(url || ''); this.__sentinelCctvMethod = String(method || 'GET').toUpperCase(); return originalOpen.call(this, method, url, ...rest) }
  XHR.prototype.send = function sentinelSend(body) { const method = this.__sentinelCctvMethod || 'GET'; const url = this.__sentinelCctvUrl || ''; const token = browserSessionToken(); if (method === 'GET' && token && isCctvRequest(url) && !/[?&]access_token=/.test(url)) { try { originalSetRequestHeader.call(this, 'Authorization', `Bearer ${token}`) } catch {} } return originalSend.call(this, body) }
  XHR.prototype.__sentinelCctvAuthInstalled = true
}

function installMetadataGuard() { const hideCollapse = () => document.querySelectorAll('button[aria-label="Collapse metadata"], button[aria-label="Expand metadata"]').forEach(button => button.remove()); hideCollapse(); const observer = new MutationObserver(hideCollapse); observer.observe(document.body, { childList: true, subtree: true }); return () => observer.disconnect() }
export function installSentinelRuntimeGuards() { if (window[INSTALL_KEY]) return; window[INSTALL_KEY] = true; installSnapshotGuard(); installCctvXHRAuth(); installMetadataGuard() }
