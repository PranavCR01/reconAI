import type { LlmConfig, SSEIncidentEvent, SSEDoneEvent, SSEErrorEvent } from '@/types'
import { getStreamUrl } from './api'

export interface SSEHandlers {
  onIncident: (event: SSEIncidentEvent) => void
  onDone: (event: SSEDoneEvent) => void
  onError: (event: SSEErrorEvent | Event) => void
  /** One row failed; the stream continues. */
  onRowError?: (event: SSEErrorEvent) => void
  /** The connection dropped and the browser is reconnecting on its own (it usually recovers). */
  onReconnecting?: () => void
}

export function connectToRun(runId: string, handlers: SSEHandlers, llmConfig?: LlmConfig, sessionId?: string, bypassCache?: boolean): () => void {
  const url = getStreamUrl(runId, llmConfig, bypassCache, sessionId)
  const es = new EventSource(url)

  es.addEventListener('incident', (e: MessageEvent) => {
    try {
      handlers.onIncident(JSON.parse(e.data) as SSEIncidentEvent)
    } catch {
      // malformed event — ignore
    }
  })

  es.addEventListener('done', (e: MessageEvent) => {
    try {
      handlers.onDone(JSON.parse(e.data) as SSEDoneEvent)
    } catch {
      handlers.onDone({ total_rows: 0 })
    }
  })

  es.addEventListener('row_error', (e: MessageEvent) => {
    try {
      handlers.onRowError?.(JSON.parse(e.data) as SSEErrorEvent)
    } catch {
      // malformed event — ignore
    }
  })

  // Stream-level failure sent by the server (no rows, rate limit): it ends the run's stream.
  es.addEventListener('error', (e: MessageEvent) => {
    if (!e.data) return // a connection error, handled by onerror below
    try {
      handlers.onError(JSON.parse(e.data) as SSEErrorEvent)
    } catch {
      handlers.onError(e)
    }
    es.close()
  })

  // Connection errors: EventSource reconnects by itself (resuming via Last-Event-ID) unless closed.
  es.onerror = (e) => {
    if (es.readyState === EventSource.CLOSED) handlers.onError(e)
    else handlers.onReconnecting?.()
  }

  return () => es.close()
}
