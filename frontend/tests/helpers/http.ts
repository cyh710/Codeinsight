import { createStore } from 'zustand'
import { vi } from 'vitest'
import type { StoreApi } from 'zustand'
import type { ChatStore, ChatMessage as Message } from '../src/store/types'

/** Minimal fake fetch Response covering every surface the API clients
 * touch: ok/status/text (error paths), clone/json (readErrorDetail). */
export function fakeResponse(init: { ok: boolean; status: number; json?: unknown; text?: string }): Response {
  const text = init.text ?? JSON.stringify(init.json ?? {})
  const res = {
    ok: init.ok,
    status: init.status,
    clone: () => res,
    json: async () => (init.json !== undefined ? init.json : JSON.parse(text)),
    text: async () => text,
  }
  return res as unknown as Response
}

/** A streaming 200 Response whose body replays the given SSE wire chunks
 * (each chunk may carry several ``event:``/``data:`` lines) then ends. */
export function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder()
  let index = 0
  const body = {
    getReader: () => ({
      read: () => {
        if (index < chunks.length) {
          index += 1
          return Promise.resolve({ done: false, value: encoder.encode(chunks[index - 1]) })
        }
        return Promise.resolve({ done: true, value: undefined })
      },
    }),
  }
  return { ok: true, status: 200, body } as unknown as Response
}

/** Shared abort bookkeeping for the hanging/silent response doubles:
 * rejects the currently-pending read (if any) and every later read. */
function abortAwareReads(signal: AbortSignal | null | undefined) {
  const abortError = () => new DOMException('Aborted', 'AbortError')
  let aborted = signal?.aborted ?? false
  let rejectPending: ((reason: unknown) => void) | null = null
  if (signal && !signal.aborted) {
    signal.addEventListener('abort', () => {
      aborted = true
      rejectPending?.(abortError())
      rejectPending = null
    }, { once: true })
  }
  return {
    read: () => {
      if (aborted) return Promise.reject(abortError())
      return new Promise((_resolve, reject) => {
        rejectPending = reject
      })
    },
    failRead: (reason: unknown) => {
      rejectPending?.(reason)
      rejectPending = null
    },
  }
}

/** A streaming 200 Response whose first read delivers ``firstChunk`` and
 * whose next read hangs until ``failRead`` rejects it — the seam for
 * client aborts and mid-stream network failures. Pass ``signal`` to make
 * the hanging read reject on abort (like a real fetch body reader). */
export function hangingSseResponse(
  firstChunk: string,
  signal?: AbortSignal | null,
): {
  response: Response
  failRead: (reason: unknown) => void
} {
  const encoder = new TextEncoder()
  let delivered = false
  const reads = abortAwareReads(signal)
  const body = {
    getReader: () => ({
      read: () => {
        if (!delivered) {
          delivered = true
          return Promise.resolve({ done: false, value: encoder.encode(firstChunk) })
        }
        return reads.read()
      },
    }),
  }
  return {
    response: { ok: true, status: 200, body } as unknown as Response,
    failRead: reads.failRead,
  }
}

/** A streaming 200 Response whose first read never resolves on its own —
 * the seam for a silently hung transport (provider stall, killed stream).
 * Pass the request ``signal`` so the watchdog's abort rejects the read. */
export function silentSseResponse(signal?: AbortSignal | null): Response {
  const reads = abortAwareReads(signal)
  const body = { getReader: () => ({ read: reads.read }) }
  return { ok: true, status: 200, body } as unknown as Response
}

export interface FetchCall {
  url: string
  init?: RequestInit
}

/** Replace global fetch with a recording stub; returns the call log. */
export function stubFetch(handler: (call: FetchCall) => Response | Promise<Response>): FetchCall[] {
  const calls: FetchCall[] = []
  vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    return handler({ url, init })
  })
  return calls
}

/** Minimal EventSource double: records the URL, lets tests emit events,
 * and tracks close() so unsubscribe paths can be asserted. */
export class FakeEventSource {
  static instances: FakeEventSource[] = []
  readonly url: string
  closed = false
  private handlers = new Map<string, (event: { data?: string }) => void>()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, handler: (event: { data?: string }) => void): void {
    this.handlers.set(type, handler)
  }

  close(): void {
    this.closed = true
  }

  emit(type: string, data: unknown): void {
    this.handlers.get(type)?.({ data: typeof data === 'string' ? data : JSON.stringify(data) })
  }
}

export function stubEventSource(): void {
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
}

/** A real zustand vanilla store carrying just the chat state streamChat
 * touches, typed as the full ChatStore for the API under test. */
export function makeChatStore(messages: Message[] = []): StoreApi<ChatStore> {
  const store = createStore(() => ({
    messages,
    streaming: false,
    branches: [],
    currentBranch: null,
    conversationId: '',
    branchLoading: false,
    branchLoadingText: '',
    branchError: '',
    webSearchEnabled: false,
    ttsEnabled: true,
    _abortController: null,
  }))
  return store as unknown as StoreApi<ChatStore>
}
