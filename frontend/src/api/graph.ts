/**
 * 关系图与时间线端点（契约 §4.5 / §7.2）。
 *
 * `kinds` 用逗号拼进查询串；对象数组这类结构一律不进 URL。
 */
import { jsonRequest } from './client'
import type { GraphQuery, GraphResponse, TimelineResponse } from './types'

export function getGraph(projectId: number, query: GraphQuery = {}): Promise<GraphResponse> {
  const params = new URLSearchParams()
  if (query.qualname) params.set('qualname', query.qualname)
  if (query.depth !== undefined) params.set('depth', String(query.depth))
  if (query.max_nodes !== undefined) params.set('max_nodes', String(query.max_nodes))
  if (query.kinds && query.kinds.length > 0) params.set('kinds', query.kinds.join(','))
  const qs = params.size ? `?${params}` : ''
  return jsonRequest<GraphResponse>(`/projects/${projectId}/graph${qs}`)
}

export function getTimeline(projectId: number, limit = 30): Promise<TimelineResponse> {
  return jsonRequest<TimelineResponse>(`/projects/${projectId}/timeline?limit=${limit}`)
}
