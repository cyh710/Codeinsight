/**
 * 建索引轮询（契约 §3.3/§3.4：POST 返回 202，前端轮询 GET /projects/{id}
 * 直到 status !== "indexing"）。抽成独立函数、`getProject` 可注入，
 * 是为了让"轮询直到终态"这件事本身能离线单测。
 */
import type { ProjectDetail } from './types'

export interface PollOptions {
  /** 轮询间隔；默认 2000ms（建索引是以秒计的批处理，1s 以下纯浪费）。 */
  intervalMs?: number
  /** 上限次数；默认 150（≈5 分钟）。到点返回最后一次拿到的详情，不抛错——
   *  超时不等于失败，调用方拿 status 自行呈现。 */
  maxAttempts?: number
  /** 每次拿到详情的回调（更新 UI 用）。 */
  onTick?: (detail: ProjectDetail) => void
}

const TERMINAL: ReadonlySet<string> = new Set(['ready', 'failed', 'stale'])

export async function waitForIndexing(
  getProject: (id: number) => Promise<ProjectDetail>,
  projectId: number,
  options: PollOptions = {},
): Promise<ProjectDetail> {
  const intervalMs = options.intervalMs ?? 2000
  const maxAttempts = options.maxAttempts ?? 150

  let detail = await getProject(projectId)
  for (let attempt = 0; attempt < maxAttempts && !TERMINAL.has(detail.status); attempt++) {
    options.onTick?.(detail)
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
    detail = await getProject(projectId)
  }
  options.onTick?.(detail)
  return detail
}
