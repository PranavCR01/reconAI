import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { connectToRun } from './sse'

type Listener = (e: { data?: string }) => void

class FakeEventSource {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSED = 2
  static last: FakeEventSource
  readyState = FakeEventSource.OPEN
  onerror: ((e: unknown) => void) | null = null
  listeners: Record<string, Listener[]> = {}
  closed = false
  constructor(public url: string) { FakeEventSource.last = this }
  addEventListener(type: string, fn: Listener) { (this.listeners[type] ??= []).push(fn) }
  emit(type: string, data?: string) { for (const fn of this.listeners[type] ?? []) fn({ data }) }
  close() { this.closed = true; this.readyState = FakeEventSource.CLOSED }
}

function connect() {
  const h = { onIncident: vi.fn(), onDone: vi.fn(), onError: vi.fn(), onRowError: vi.fn(), onReconnecting: vi.fn() }
  connectToRun('run-1', h)
  return { h, es: FakeEventSource.last }
}

beforeEach(() => { vi.stubGlobal('EventSource', FakeEventSource) })
afterEach(() => { vi.unstubAllGlobals() })

describe('connectToRun', () => {
  it('a dropped connection the browser is retrying is "reconnecting", not an error', () => {
    const { h, es } = connect()
    es.readyState = FakeEventSource.CONNECTING
    es.onerror?.({})
    es.emit('error') // the browser also dispatches a data-less "error" event
    expect(h.onReconnecting).toHaveBeenCalledTimes(1)
    expect(h.onError).not.toHaveBeenCalled()
  })

  it('a closed connection is an error', () => {
    const { h, es } = connect()
    es.readyState = FakeEventSource.CLOSED
    es.onerror?.({})
    expect(h.onError).toHaveBeenCalledTimes(1)
  })

  it('one failed row is reported separately and does not end the stream', () => {
    const { h, es } = connect()
    es.emit('row_error', JSON.stringify({ row_index: 3, row_id: 'r', error: 'boom' }))
    expect(h.onRowError).toHaveBeenCalledWith({ row_index: 3, row_id: 'r', error: 'boom' })
    expect(h.onError).not.toHaveBeenCalled()
    expect(es.closed).toBe(false)
  })

  it('a server-sent stream failure (e.g. rate limit) is an error and closes the stream', () => {
    const { h, es } = connect()
    es.emit('error', JSON.stringify({ detail: 'rate limited' }))
    expect(h.onError).toHaveBeenCalledWith({ detail: 'rate limited' })
    expect(es.closed).toBe(true)
  })
})
