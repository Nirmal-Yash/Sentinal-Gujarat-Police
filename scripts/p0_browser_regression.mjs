import fs from 'node:fs'
import path from 'node:path'

const ROOT = process.cwd()
const failures = []

function read(relativePath) {
  const file = path.join(ROOT, relativePath)
  if (!fs.existsSync(file)) {
    failures.push(`${relativePath} is missing`)
    return ''
  }
  return fs.readFileSync(file, 'utf8')
}

function requireText(text, fragment, message) {
  if (!text.includes(fragment)) failures.push(message)
  else console.log(`[OK] ${message}`)
}

function requirePattern(text, pattern, message) {
  if (!pattern.test(text)) failures.push(message)
  else console.log(`[OK] ${message}`)
}

const runtime = read('dashboard/src/runtimeGuards.js')
const main = read('dashboard/src/main.jsx')
const cctv = read('api/routes/cctv.py')
const models = read('api/models.py')
const compose = read('docker-compose.yml')
const packageJson = read('dashboard/package.json')
const alerts = read('dashboard/src/components/AlertsPage.jsx')
const navbar = read('dashboard/src/components/Navbar.jsx')

requireText(runtime, 'SNAPSHOT_CACHE_TTL_MS = 15000', 'snapshot fallback cache is 15 seconds')
requireText(runtime, "!/^\\/api\\/cameras\\/[^/]+\\/snapshot$/.test(url.pathname)", 'snapshot guard targets camera snapshot API')
requireText(runtime, 'SNAPSHOT_INFLIGHT', 'concurrent snapshot requests are deduplicated')
requireText(runtime, 'SNAPSHOT_CACHE.set(key, { timestamp: Date.now(), result })', 'snapshot failures are also throttled for 15 seconds')
requireText(runtime, 'installCctvXHRAuth()', 'browser CCTV XHR authentication is installed')
requireText(runtime, 'parsed.origin === window.location.origin', 'CCTV authentication stays same-origin')
requireText(runtime, "'Authorization', `Bearer ${token}`", 'browser attaches Sentinel JWT to CCTV XHRs')
requireText(main, 'installSentinelRuntimeGuards()', 'runtime guards are installed by the application entrypoint')
requireText(cctv, 'prefix="/cctv"', 'authenticated CCTV proxy route exists')
requireText(cctv, 'Invalid or expired CCTV playback token', 'CCTV playback token validation exists')
requireText(cctv, 'principal_from_token', 'CCTV proxy accepts the authenticated Sentinel session')
requireText(cctv, 'CCTV playback authentication required', 'CCTV proxy rejects unauthenticated playback')
requireText(cctv, 'X-Content-Type-Options', 'CCTV proxy sets browser hardening headers')
requireText(models, 'playback_id', 'camera playback uses an authoritative provider identifier')
requireText(models, 'external_id', 'camera playback prefers external_id when it is cam01-style')
requirePattern(models, /value\["hls_url"\]\s*=\s*f?["']\/api\/cctv\/\{provider_id\}\/index\.m3u8\{token_query\}/, 'camera API emits signed same-origin HLS URLs')
requireText(compose, 'CCTV_PASSWORD', 'Compose injects the server-side CCTV password')
requireText(packageJson, '"hls.js"', 'dashboard retains HLS playback support')

if (compose.includes('live.corp8.cloud')) failures.push('deprecated live.corp8.cloud reference remains in docker-compose.yml')
else console.log('[OK] deprecated live.corp8.cloud is absent from docker-compose.yml')

requireText(alerts, 'Acknowledge', 'alerts workspace exposes acknowledgement actions')
requireText(alerts, 'Investigate', 'alerts workspace exposes investigation actions')
requireText(alerts, 'Resolve', 'alerts workspace exposes resolution actions')
requireText(alerts, 'Close', 'alerts workspace exposes close actions')
requireText(alerts, 'AlertEvidence', 'alerts workspace loads evidence through the evidence API')
requireText(alerts, 'LAST 24H', 'alerts workspace provides date presets')
requireText(alerts, 'setLoading(false)', 'alerts refresh always clears loading state')
requireText(navbar, 'sentinel-alert-count-badge', 'sidebar renders a dedicated alert count badge')

if (failures.length) {
  console.error(`\n${failures.length} P0 browser regression gate(s) failed.`)
  for (const failure of failures) console.error(`[FAIL] ${failure}`)
  process.exit(1)
}

console.log('\nAll P0 browser regression gates passed.')
