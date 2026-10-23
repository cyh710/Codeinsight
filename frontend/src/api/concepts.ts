/**
 * 知识层端点（契约 §6）。B 线检测器落地前这些端点可能返回空列表——
 * 前端按空状态渲染，不造数据。
 */
import { jsonRequest } from './client'
import type {
  ConceptDepth,
  ConceptDetail,
  ConceptExplanation,
  ConceptInstance,
  ConceptListItem,
  ListResponse,
} from './types'

export function listConcepts(
  projectId: number,
  filter: { q?: string; category?: string } = {},
): Promise<ListResponse<ConceptListItem>> {
  const params = new URLSearchParams()
  if (filter.q) params.set('q', filter.q)
  if (filter.category) params.set('category', filter.category)
  const qs = params.size ? `?${params}` : ''
  return jsonRequest<ListResponse<ConceptListItem>>(`/projects/${projectId}/concepts${qs}`)
}

export function getConcept(projectId: number, conceptId: string): Promise<ConceptDetail> {
  return jsonRequest<ConceptDetail>(`/projects/${projectId}/concepts/${encodeURIComponent(conceptId)}`)
}

export function listConceptInstances(
  projectId: number,
  conceptId: string,
): Promise<ListResponse<ConceptInstance>> {
  return jsonRequest<ListResponse<ConceptInstance>>(
    `/projects/${projectId}/concepts/${encodeURIComponent(conceptId)}/instances`,
  )
}

export function explainConcept(
  projectId: number,
  conceptId: string,
  depth: ConceptDepth,
): Promise<ConceptExplanation> {
  return jsonRequest<ConceptExplanation>(
    `/projects/${projectId}/concepts/${encodeURIComponent(conceptId)}/explain`,
    { method: 'POST', body: JSON.stringify({ depth }) },
  )
}
