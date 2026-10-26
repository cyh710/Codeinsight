/**
 * HTTP 客户端基础件（结构抄织忆 `api/agent.ts`，错误形状换成 CodeInsight 契约 §0.3）。
 *
 * 约定：
 * - 浏览器侧一律走 `/api` 前缀（vite proxy 剥掉后转发到 8020）。
 * - 非 2xx 的 body **只有一种形状**：`{error: {code, title, hint, detail}}`。
 *   未知 `code` 按 `internal_error` 兜底（契约 §0.3"不要白屏"）。
 * - JSON 字段 snake_case，前端不做 camelCase 转换（契约 §0.6）。
 */
import type { ApiErrorBody, ApiErrorCode } from './types'

export const BASE = '/api'

const KNOWN_CODES: readonly ApiErrorCode[] = [
  'conversation_busy', 'reading_invalid', 'aborted', 'not_found',
  'bad_request',
  'project_not_found',
  'symbol_not_found',
  'concept_not_found',
  'not_indexed',
  'index_running',
  'upstream_error',
  'timeout',
  'internal_error',
]

/** 后端错误（契约 §0.3 的唯一变体）。前端可以 switch `code`。 */
export class ApiError extends Error {
  readonly code: ApiErrorCode
  readonly title: string
  readonly hint: string
  readonly detail: string
  readonly status: number

  constructor(init: {
    code: ApiErrorCode
    title: string
    hint: string
    detail: string
    status: number
  }) {
    super(`${init.title}（${init.code}）`)
    this.name = 'ApiError'
    this.code = init.code
    this.title = init.title
    this.hint = init.hint
    this.detail = init.detail
    this.status = init.status
  }
}

const FALLBACK_ERROR = {
  code: 'internal_error' as ApiErrorCode,
  title: '服务异常',
  hint: '请稍后重试；若持续出现，请检查本地后端服务是否正常运行。',
  detail: '',
}

/** 把任意失败响应/网络异常归一成 `ApiError`——调用方永远拿到同一个形状。 */
export async function toApiError(res: Response | null, networkDetail?: string): Promise<ApiError> {
  if (!res) {
    // 网络层异常没有 HTTP 状态可报：status 用 0 标记"请求未到达"。
    return new ApiError({ ...FALLBACK_ERROR, status: 0, detail: networkDetail ?? '网络请求未发出' })
  }
  const body = await readErrorBody(res).catch(() => null)
  const err = body?.error
  const code =
    err?.code && (KNOWN_CODES as readonly string[]).includes(err.code)
      ? (err.code as ApiErrorCode)
      : 'internal_error'
  return new ApiError({
    code,
    title: err?.title || FALLBACK_ERROR.title,
    hint: err?.hint || FALLBACK_ERROR.hint,
    detail: err?.detail || `HTTP ${res.status}`,
    status: res.status,
  })
}

/** 非 2xx 的 body 是 §0.3 的错误形状；拿不到 JSON 时返回 null。 */
async function readErrorBody(res: Response): Promise<Partial<ApiErrorBody> | null> {
  try {
    return (await res.clone().json()) as Partial<ApiErrorBody>
  } catch {
    return null
  }
}

/** JSON 请求统一入口。非 2xx 抛 `ApiError`；2xx 按泛型解析。 */
export async function jsonRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...init?.headers,
      },
    })
  } catch (e) {
    throw await toApiError(null, (e as Error).message)
  }
  if (!res.ok) {
    throw await toApiError(res)
  }
  return (await res.json()) as T
}
