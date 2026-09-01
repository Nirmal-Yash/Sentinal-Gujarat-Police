import L from 'leaflet'

const INSTALL_KEY = '__sentinelSmoothLeafletNavigationInstalled'
const original = {
  setView: L.Map.prototype.setView,
  panTo: L.Map.prototype.panTo,
  fitBounds: L.Map.prototype.fitBounds,
}

export function installSmoothLeafletNavigation() {
  if (globalThis[INSTALL_KEY]) return
  globalThis[INSTALL_KEY] = true

  L.Map.prototype.setView = function sentinelSetView(center, zoom, options) {
    const targetZoom = Number(zoom)
    if (options?.animate === false || !Number.isFinite(targetZoom) || targetZoom < 15) {
      return original.setView.call(this, center, zoom, options)
    }
    return this.flyTo(center, targetZoom, {
      duration: 1.5,
      easeLinearity: 0.25,
      animate: true,
    })
  }

  L.Map.prototype.panTo = function sentinelPanTo(center, options) {
    if (options?.animate === false) return original.panTo.call(this, center, options)
    return this.flyTo(center, this.getZoom(), {
      duration: 1.1,
      easeLinearity: 0.25,
      animate: true,
    })
  }

  L.Map.prototype.fitBounds = function sentinelFitBounds(bounds, options) {
    if (!options || !Number.isFinite(Number(options.maxZoom))) {
      return original.fitBounds.call(this, bounds, options)
    }
    return this.flyToBounds(bounds, {
      ...options,
      duration: options.maxZoom >= 15 ? 1.0 : 0.8,
      easeLinearity: options.maxZoom >= 15 ? 0.25 : 0.35,
      animate: true,
    })
  }
}
