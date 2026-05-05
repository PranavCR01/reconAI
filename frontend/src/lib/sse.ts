import type { LlmConfig, SSEIncidentEvent, SSEDoneEvent, SSEErrorEvent } from '@/types'
import { getStreamUrl } from './api'

export interface SSEHandlers {
  onIncident: (event: SSEIncidentEvent) => void
  onDone: (event: SSEDoneEvent) => void
  onError: (event: SSEErrorEvent | Event) => void
}

export function connectToRun(runId: string, handlers: SSEHandlers, llmConfig?: LlmConfig): () => void {
  const url = getStreamUrl(runId, llmConfig)
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

  es.addEventListener('error', (e: MessageEvent) => {
    try {
      handlers.onError(JSON.parse(e.data) as SSEErrorEvent)
    } catch {
      handlers.onError(e)
    }
  })

  es.onerror = (e) => {
    handlers.onError(e)
  }

  return () => es.close()
}
