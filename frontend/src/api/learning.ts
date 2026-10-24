/** 全局教材与项目实例使用不同端点；目录浏览不需要项目。 */
import { jsonRequest } from './client'
import type { ConceptInstance, KnowledgeSearch, KnowledgeTopic, KnowledgeTree } from './types'

export const getKnowledgeTree = () => jsonRequest<KnowledgeTree>('/knowledge/tree')
export const getKnowledgeTopic = (id: string) =>
  jsonRequest<KnowledgeTopic>(`/knowledge/topics/${encodeURIComponent(id)}`)
export const searchKnowledge = (q: string) =>
  jsonRequest<KnowledgeSearch>(`/knowledge/search?q=${encodeURIComponent(q)}&limit=12`)
export const getTopicInstances = (projectId: number, topicId: string) =>
  jsonRequest<{ items: ConceptInstance[]; status: string; limit: number }>(
    `/projects/${projectId}/knowledge/topics/${encodeURIComponent(topicId)}/instances`,
  )
export const readProjectCode = (projectId: number, path: string, line = 1) =>
  jsonRequest<{ path: string; start_line: number; end_line: number; content: string }>(
    `/projects/${projectId}/code?path=${encodeURIComponent(path)}&start_line=${line}`,
  )
