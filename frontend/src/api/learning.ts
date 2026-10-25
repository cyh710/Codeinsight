/** 全局教材与项目实例使用不同端点；目录浏览不需要项目。 */
import { jsonRequest } from './client'
import type { ConceptInstance, KnowledgeSearch, KnowledgeTopic, KnowledgeTree } from './types'

export const getKnowledgeTree = () => jsonRequest<KnowledgeTree>('/knowledge/tree')
export const getKnowledgeTopic = (id: string) =>
  jsonRequest<KnowledgeTopic>(`/knowledge/topics/${encodeURIComponent(id)}`)
// limit 是**章节**数：一篇文章的多个章节都会命中，界面按文章合并。
// 取 40 个章节，合并后通常能凑出好几篇文章。
export const searchKnowledge = (q: string) =>
  jsonRequest<KnowledgeSearch>(`/knowledge/search?q=${encodeURIComponent(q)}&limit=40`)
export const getTopicInstances = (projectId: number, topicId: string) =>
  jsonRequest<{ items: ConceptInstance[]; status: string; limit: number }>(
    `/projects/${projectId}/knowledge/topics/${encodeURIComponent(topicId)}/instances`,
  )
export const readProjectCode = (projectId: number, path: string, line = 1) =>
  jsonRequest<{ path: string; start_line: number; end_line: number; content: string; total_lines: number; head_commit: string | null; content_sha256: string }>(
    `/projects/${projectId}/code?path=${encodeURIComponent(path)}&start_line=${line}`,
  )
