/**
 * 数据源开关：mock（默认）与真实后端之间二选一，接口形状完全一致。
 *
 * 默认 mock：C 线开发期后端尚未就绪，且 mock 数据是真实解析快照——
 * 切到真实模式时只是换实现，不改任何调用方。要连真后端：
 * `VITE_CI_MOCK=0 npm run dev`（后端须在 8020 端口）。
 */
import * as projects from './projects'
import * as concepts from './concepts'
import * as graph from './graph'
import { mockApi } from './mock'
import { jsonRequest } from './client'
import { streamQuery } from './stream'
import type { QueryRequest, QueryResponse } from './types'

const USE_MOCK = import.meta.env.VITE_CI_MOCK === '1'

function realQuery(request: QueryRequest): Promise<QueryResponse> {
  return jsonRequest<QueryResponse>('/query', { method: 'POST', body: JSON.stringify(request) })
}

const realApi = {
  ...projects,
  ...concepts,
  ...graph,
  query: realQuery,
  streamQuery,
}

export const api = USE_MOCK ? mockApi : realApi
export const isMockMode = USE_MOCK
