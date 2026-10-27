/**
 * 建索引轮询（契约 §3.3/§3.4：POST 返回 202，前端轮询 GET /projects/{id}
 * 直到 status !== "indexing"）。抽成独立函数、`getProject` 可注入，
 * 是为了让"轮询直到终态"这件事本身能离线单测。
 */
import type { ProjectDetail } from './types'
import { ApiError } from './client'

export interface PollOptions {
  /** 轮询间隔；默认 2000ms（建索引是以秒计的批处理，1s 以下纯浪费）。 */
  intervalMs?: number
  /** 轮询上限；默认 150 次（正常约 5 分钟，故障时退避），失败也计次。
   *  到点正常返回本次详情；仍不可读则抛出原错误，交由调用方提供恢复入口。 */
  maxAttempts?: number
  /** 每次拿到详情的回调（更新 UI 用）。 */
  onTick?: (detail: ProjectDetail) => void
  /** 暂时不可读时保留提示，但在原有次数预算内继续检查。 */
  onError?: (error: unknown) => void
  signal?: AbortSignal
}

const TERMINAL: ReadonlySet<string> = new Set(['ready', 'failed', 'stale'])

function retryable(error: unknown): boolean {
  return error instanceof ApiError ? error.status === 0 || error.status >= 500 : error instanceof TypeError
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    signal?.throwIfAborted()
    const abort = () => { clearTimeout(timer); reject(signal!.reason) }
    const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve() }, ms)
    signal?.addEventListener('abort', abort, { once: true })
  })
}

export async function waitForIndexing(
  getProject: (id: number) => Promise<ProjectDetail>,
  projectId: number,
  options: PollOptions = {},
): Promise<ProjectDetail> {
  const intervalMs = options.intervalMs ?? 2000
  const maxAttempts = options.maxAttempts ?? 150

  let failures = 0
  for (let attempt = 0; ; attempt++) {
    options.signal?.throwIfAborted()
    try {
      const detail = await getProject(projectId)
      options.signal?.throwIfAborted()
      failures = 0
      options.onTick?.(detail)
      if (TERMINAL.has(detail.status) || attempt >= maxAttempts) return detail
    } catch (error) {
      options.signal?.throwIfAborted()
      if (!retryable(error) || attempt >= maxAttempts) throw error
      failures++
      options.onError?.(error)
    }
    await delay(Math.min(intervalMs * 2 ** Math.min(failures, 3), 10_000), options.signal)
  }
}
