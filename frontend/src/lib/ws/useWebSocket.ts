import { useCallback, useEffect, useRef, useState } from 'react'
import { App } from 'antd'
import type { AgentEvent } from '@/types/agent'
import { useAuthStore } from '@/lib/store/authStore'

const MAX_EVENTS = 100
const MAX_RETRY = 6

type ConnectionStatus = 'connecting' | 'open' | 'closed' | 'error'

interface UseWebSocketOptions {
  onEvent?: (event: AgentEvent) => void
  onNotification?: (event: AgentEvent) => void
}

interface UseWebSocketResult {
  events: AgentEvent[]
  status: ConnectionStatus
  send: (data: Record<string, unknown>) => void
  clear: () => void
}

function buildWsUrl(learnerId: string, token: string): string {
  const base = (import.meta.env.VITE_WS_BASE as string | undefined)?.replace(/\/$/, '')
  const path = `/ws/${encodeURIComponent(learnerId)}?token=${encodeURIComponent(token)}`
  if (base) return `${base}${path}`
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${path}`
}

/** 安全关闭:先摘掉回调,避免异步 onclose 误触发重连逻辑 */
function disposeSocket(ws: WebSocket | null) {
  if (!ws) return
  ws.onopen = null
  ws.onmessage = null
  ws.onerror = null
  ws.onclose = null
  if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
    try {
      ws.close(1000, 'dispose')
    } catch {
      /* ignore */
    }
  }
}

/**
 * WebSocket Hook
 * - 用 generation 标记连接代次,StrictMode / 重连时旧 onclose 全部作废
 * - 开发可用 VITE_WS_BASE 直连后端
 */
export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketResult {
  const { onEvent, onNotification } = options
  const { message } = App.useApp()
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [status, setStatus] = useState<ConnectionStatus>('connecting')

  const wsRef = useRef<WebSocket | null>(null)
  const genRef = useRef(0)
  const retryRef = useRef(0)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onEventRef = useRef(onEvent)
  const onNotificationRef = useRef(onNotification)
  const messageRef = useRef(message)
  const mountedRef = useRef(false)

  useEffect(() => {
    onEventRef.current = onEvent
    onNotificationRef.current = onNotification
  }, [onEvent, onNotification])

  useEffect(() => {
    messageRef.current = message
  }, [message])

  const token = useAuthStore((s) => s.token)
  const learnerId = useAuthStore((s) => s.user?.learner_id ?? null)

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current)
      reconnectTimer.current = null
    }
  }, [])

  const connect = useCallback(() => {
    if (!mountedRef.current) return
    if (!learnerId || !token) {
      setStatus('closed')
      return
    }

    clearReconnectTimer()

    // 作废上一轮连接的全部回调
    const gen = ++genRef.current
    disposeSocket(wsRef.current)
    wsRef.current = null

    const url = buildWsUrl(String(learnerId), token)
    setStatus('connecting')

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      if (gen !== genRef.current || !mountedRef.current) return
      setStatus('open')
      retryRef.current = 0
    }

    ws.onmessage = (msg) => {
      if (gen !== genRef.current || !mountedRef.current) return
      let parsed: Record<string, unknown>
      try {
        parsed = JSON.parse(msg.data)
      } catch {
        return
      }

      if (parsed.type === 'ping') {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ action: 'pong' }))
        }
        return
      }

      if (parsed.type === 'error') {
        messageRef.current.error(`WebSocket: ${parsed.message ?? '未知错误'}`)
        return
      }

      if (parsed.type === 'event' || parsed.event_type) {
        const event = {
          event_type: parsed.event_type as AgentEvent['event_type'],
          source: parsed.source as AgentEvent['source'],
          data: (parsed.data ?? {}) as Record<string, unknown>,
          timestamp: (parsed.timestamp as string) ?? new Date().toISOString(),
        } satisfies AgentEvent
        setEvents((prev) => [event, ...prev].slice(0, MAX_EVENTS))
        onEventRef.current?.(event)
        if (event.event_type === 'notification' || event.source === 'api') {
          onNotificationRef.current?.(event)
        }
      }
    }

    ws.onclose = (ev) => {
      // 代次已变:这是被主动 dispose 的旧连接,忽略
      if (gen !== genRef.current || !mountedRef.current) return
      wsRef.current = null
      setStatus('closed')

      if (ev.code === 1008) {
        messageRef.current.error('WebSocket 鉴权失败,请重新登录')
        return
      }
      if (ev.code === 4002) {
        messageRef.current.warning('连接被挤占,正在重连...')
      } else if (ev.code === 4001) {
        messageRef.current.warning('WebSocket 心跳超时,正在重连...')
      }

      const attempt = retryRef.current
      if (attempt >= MAX_RETRY) return
      const delay = Math.min(1000 * 2 ** attempt, 30_000)
      retryRef.current = attempt + 1
      reconnectTimer.current = setTimeout(() => {
        if (gen === genRef.current && mountedRef.current) connect()
      }, delay)
    }

    ws.onerror = () => {
      if (gen !== genRef.current || !mountedRef.current) return
      setStatus('error')
    }
  }, [learnerId, token, clearReconnectTimer])

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      clearReconnectTimer()
      genRef.current += 1
      disposeSocket(wsRef.current)
      wsRef.current = null
    }
  }, [connect, clearReconnectTimer])

  const send = useCallback((data: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  const clear = useCallback(() => setEvents([]), [])

  return { events, status, send, clear }
}
