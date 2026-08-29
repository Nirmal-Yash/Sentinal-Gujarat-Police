export const VALID_ROUTES = new Set(['/feeds','/map','/alerts','/investigations','/test'])

export function normalizePath(pathname = '/') {
  if (pathname === '/dashboard' || pathname === '/') return '/feeds'
  return VALID_ROUTES.has(pathname) ? pathname : '/feeds'
}

export function routeFromLocation(location = window.location) {
  return normalizePath(location.pathname)
}

export function navigateHistory(target, { replace = false } = {}) {
  const next = normalizePath(target)
  const current = normalizePath(window.location.pathname)
  if (current !== next) {
    const method = replace ? 'replaceState' : 'pushState'
    window.history[method]({ sentinelRoute: next }, '', next)
  }
  window.dispatchEvent(new PopStateEvent('popstate'))
  return next
}
