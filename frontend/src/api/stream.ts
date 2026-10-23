/**
 * SSE 解析与流式问答（结构抄织忆 `api/stream.ts`，事件词汇表换成契约 §8.3）。
 *
 * 事件序约束（契约 §8.3）：`meta` 恰好一次开头，`answer`/`done` 各恰好一次，
 * `done` **必发**——`error` 之后也要发，前端的收尾逻辑因此只认 `done`。
 *
 * watchdog 两档与织忆同：首字节 120s / 流中静默 30s。没有它，一次挂死的流
 * 会把 `streaming=true` 永远留在 store 里，之后的每次发送都被静默拒绝。
 */
import { BASE } from './client'
import type {
  ApiErrorCode,
  QueryRequest,
  SseEvent,
  SseEventName,
} from './types'

export const STREAM_WATCHDOG_SILENCE_MS = 30_000
export const STREAM_WATCHDOG_FIRST_EVENT_MS = 120_000
export const STREAM_WATCHDOG_TICK_MS = 5_000

export type SseHandler = (event: SseEvent) => void

/**
 * 从 fetch 的 body reader 里解析 SSE 帧。
 *
 * 手写解析（`getReader()` + `TextDecoder` + 按行切）而不是 `EventSource`：
 * 本端点是 POST，`EventSource` 只支持 GET。`event:` 行声明事件名，
 * 紧随的 `data:` 行是单行 JSON（契约保证不含裸换行）。
 */
export async function readSseBody(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  onEvent: SseHandler,
): Promise<void> {
  const decoder = new TextDecoder()
  let buffer = ''
  let currentEvent: SseEventName | null = null

  const handleLine = (line: string) => {
    if (line.startsWith('event: ')) {
      currentEvent = line.slice(7).trim() as SseEventName
      return
    }
    if (!line.startsWith('data: ')) return
    const payload = line.slice(6).trim()
    if (!payload || !currentEvent) return
    try {
      onEvent({ event: currentEvent, data: JSON.parse(payload) } as SseEvent)
    } catch {
      // 坏帧跳过：SSE 的丢帧不该毁掉整条流，后续事件仍能推进状态。
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) handleLine(line)
  }
  if (buffer.trim()) handleLine(buffer)
}

export interface StreamResult {
  /** watchdog 或网络错误时为 true；正常走到 `done` 为 false。 */
  aborted: boolean
  error?: { code: ApiErrorCode | 'network' | 'timeout'; title: string; hint: string }
}

/**
 * 发起流式问答并把事件交给 `onEvent`。
 *
 * `done` 或流自然结束前不 resolve；`error` 事件**不会**中断读取（契约：
 * error 之后仍然会发 done），只有 watchdog 静默与网络层异常会提前收场。
 */
export async function streamQuery(
  request: QueryRequest,
  onEvent: SseHandler,
  signal?: AbortSignal,
): Promise<StreamResult> {
  const controller = new AbortController()
  signal?.addEventListener('abort', () => controller.abort(), { once: true })
  // 外部 signal 已中止时 addEventListener 不会再触发——必须显式联动，
  // 否则内部 controller 永远不中止，"停止"按钮在建立连接前按下会失效。
  if (signal?.aborted) controller.abort()

  let firstActivitySeen = false
  let lastActivityAt = Date.now()
  const watchdog = setInterval(() => {
    const limit = firstActivitySeen
      ? STREAM_WATCHDOG_SILENCE_MS
      : STREAM_WATCHDOG_FIRST_EVENT_MS
    if (Date.now() - lastActivityAt > limit) controller.abort()
  }, STREAM_WATCHDOG_TICK_MS)

  const touch = () => {
    firstActivitySeen = true
    lastActivityAt = Date.now()
  }

  try {
    const res = await fetch(`${BASE}/query/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal: controller.signal,
    })
    if (!res.ok || !res.body) {
      // 非 2xx：body 是 §0.3 的错误形状，交给统一的解析；这里只负责归一成 StreamResult。
      const text = await res.text().catch(() => '')
      return { aborted: true, error: { code: 'internal_error', title: `请求失败（HTTP ${res.status}）`, hint: text.slice(0, 300) } }
    }
    touch()
    await readSseBody(res.body.getReader(), (event) => {
      touch()
      onEvent(event)
    })
    return { aborted: false }
  } catch (e) {
    const err = e as Error
    if (err.name === 'AbortError') {
      if (signal?.aborted) {
        // 用户主动停止：不算错误，但也不是正常 done。
        return { aborted: true }
      }
      return {
        aborted: true,
        error: {
          code: 'timeout',
          title: '回复超时',
          hint: firstActivitySeen
            ? '回复中途超过 30 秒没有新内容，连接已自动断开，请重试。'
            : '超过 120 秒没有收到任何回复内容，连接已自动断开，请重试。',
        },
      }
    }
    return {
      aborted: true,
      error: { code: 'network', title: '连接错误', hint: err.message || '网络异常，请检查后端是否正在运行。' },
    }
  } finally {
    clearInterval(watchdog)
  }
}
