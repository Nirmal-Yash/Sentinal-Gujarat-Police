export function notifyToast(message, type = 'info') {
  window.dispatchEvent(new CustomEvent('sentinel:toast', { detail: { message, type } }))
}
