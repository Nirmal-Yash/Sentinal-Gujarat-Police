import { useEffect, useRef, useCallback } from 'react'

export function useWebSocket(url, onMessage) {
  const wsRef      = useRef(null)
  const retryRef   = useRef(null)
  const mountedRef = useRef(true)

  const connect = useCallback(() => {
    if (!mountedRef.current || !url) return
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen    = () => { clearTimeout(retryRef.current) }
    ws.onmessage = e => { try { onMessage(JSON.parse(e.data)) } catch {} }
    ws.onerror   = () => ws.close()
    ws.onclose   = () => {
      if (mountedRef.current)
        retryRef.current = setTimeout(connect, 3000)
    }

    // Send keep-alive ping every 25 s
    const ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send('ping')
    }, 25000)
    ws._ping = ping
  }, [url, onMessage])

  useEffect(() => {
    mountedRef.current = true
    if (url) connect()
    return () => {
      mountedRef.current = false
      clearTimeout(retryRef.current)
      if (wsRef.current) {
        clearInterval(wsRef.current._ping)
        wsRef.current.close()
      }
    }
  }, [connect])
}
