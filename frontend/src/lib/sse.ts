// Typed wrapper around the run event stream: GET /api/runs/{id}/events
// Handles every named event in docs/API_CONTRACT.md, reconnects on drop
// (unless the stream ended cleanly via a terminal event), and tears down
// cleanly when the caller unsubscribes.

import type { SseEventMap, SseEventName } from './types'
import { MOCK_MODE } from './api'

type Handlers = Partial<{ [K in SseEventName]: (data: SseEventMap[K]) => void }> & {
  onOpen?: () => void
  onError?: (err: Event) => void
  /** fires once, after run_completed / run_failed / cancelled */
  onDone?: () => void
}

const TERMINAL_EVENTS: SseEventName[] = ['run_completed', 'run_failed', 'cancelled']

export interface RunEventStream {
  close: () => void
}

// In mock mode there is no server, so the stream is driven by an in-memory
// simulator (src/lib/mock/stream.ts) that emits the same event shapes.
let mockSubscribe: typeof import('./mock/stream').mockSubscribeToRunEvents | null = null
if (MOCK_MODE) {
  ;({ mockSubscribeToRunEvents: mockSubscribe } = await import('./mock/stream'))
}

/**
 * Subscribe to a run's live event stream. Returns a handle with `close()`
 * for teardown (call it from a useEffect cleanup).
 */
export function subscribeToRunEvents(runId: number, handlers: Handlers): RunEventStream {
  if (MOCK_MODE && mockSubscribe) {
    return mockSubscribe(runId, handlers)
  }

  let closed = false
  let es: EventSource | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let attempt = 0
  let done = false

  const connect = () => {
    if (closed) return
    es = new EventSource(`/api/runs/${runId}/events`)

    es.onopen = () => {
      attempt = 0
      handlers.onOpen?.()
    }

    for (const name of Object.keys(EVENT_NAMES) as SseEventName[]) {
      es.addEventListener(name, (evt) => {
        const messageEvent = evt as MessageEvent<string>
        let data: unknown
        try {
          data = JSON.parse(messageEvent.data)
        } catch {
          return
        }
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        ;(handlers[name] as any)?.(data)
        if (TERMINAL_EVENTS.includes(name) && !done) {
          done = true
          handlers.onDone?.()
          close()
        }
      })
    }

    es.onerror = (err) => {
      handlers.onError?.(err)
      if (closed || done) return
      es?.close()
      es = null
      attempt += 1
      const delay = Math.min(1000 * 2 ** attempt, 10_000)
      reconnectTimer = setTimeout(connect, delay)
    }
  }

  const close = () => {
    closed = true
    if (reconnectTimer) clearTimeout(reconnectTimer)
    es?.close()
    es = null
  }

  connect()
  return { close }
}

const EVENT_NAMES: Record<SseEventName, true> = {
  run_started: true,
  case_started: true,
  case_completed: true,
  case_failed: true,
  progress: true,
  run_completed: true,
  run_failed: true,
  cancelled: true,
}
