import type { CodeReadingContext, LearningTarget, ReadingContext } from '../../api/types'
import { workbenchStore } from '../../store/workbenchStore'

export function openCode(target: CodeReadingContext) {
  workbenchStore.getState().selectFile(target.path, target.lineno, target.head_commit, target.index_epoch, target.source_kind, target.content_sha256)
}
export function knowledgeTarget(target: ReadingContext): LearningTarget | null {
  if (target.kind !== 'knowledge') return null
  return { topic_id: target.topic_id, section_id: target.section_id ?? null,
    title: target.title ?? target.topic_id, section_title: target.section_title,
    version: target.version, href: `/learn/${target.topic_id}${target.section_id ? `#${target.section_id}` : ''}` }
}
export function openRelated(target: LearningTarget, projectId: number, conversationId: string, requestId?: string) {
  if (requestId) workbenchStore.getState().openMaterial({ mode: 'exploration', projectId, conversationId, requestId, target })
  else workbenchStore.getState().openKnowledge(target)
}
