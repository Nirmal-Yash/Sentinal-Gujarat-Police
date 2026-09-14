const INDIAN_PLATE_RE = /^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{1,4}$/
const CAMERA_LABEL_RE = /^[A-Za-z0-9 ,.\-]{2,255}$/
const USERNAME_RE = /^[a-zA-Z0-9_.-]{3,64}$/

export function normalizePlate(value) {
  const normalized = String(value || '').toUpperCase().replace(/[^A-Z0-9]/g, '')
  return normalized || ''
}

export function isValidIndianPlate(value) {
  const normalized = normalizePlate(value)
  return normalized.length >= 3 && INDIAN_PLATE_RE.test(normalized)
}

export function plateValidationMessage(value) {
  const text = String(value || '').trim()
  if (!text) return 'Plate is required'
  if (text.length < 3) return 'Plate must be at least 3 characters'
  if (text.length > 20) return 'Plate must be at most 20 characters'
  if (!isValidIndianPlate(text)) return 'Use Indian plate format, e.g. GJ01AB1234'
  return ''
}

export function isValidCameraLabel(value) {
  const text = String(value || '').trim()
  return Boolean(text && CAMERA_LABEL_RE.test(text))
}

export function cameraLabelValidationMessage(value) {
  const text = String(value || '').trim()
  if (!text) return 'Camera label is required'
  if (!isValidCameraLabel(text)) return 'Use letters, numbers, spaces, comma, dot, or hyphen (2–255 chars)'
  return ''
}

export function isValidUsername(value) {
  const text = String(value || '').trim()
  return Boolean(text && USERNAME_RE.test(text))
}

export function usernameValidationMessage(value) {
  const text = String(value || '').trim()
  if (!text) return 'Username is required'
  if (!isValidUsername(text)) return 'Username must be 3–64 characters (letters, numbers, _, ., -)'
  return ''
}

export function isValidPassword(value) {
  const text = String(value || '')
  return text.length >= 1 && text.length <= 128
}

export function isValidPlateFilter(value) {
  const text = String(value || '').trim()
  if (!text) return true
  return text.length <= 20 && /^[A-Za-z0-9\- ]+$/.test(text)
}

export function isValidLatitude(value) {
  const n = Number(value)
  return Number.isFinite(n) && n >= -90 && n <= 90
}

export function isValidLongitude(value) {
  const n = Number(value)
  return Number.isFinite(n) && n >= -180 && n <= 180
}
