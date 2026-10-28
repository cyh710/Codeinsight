import type { CodeReadingContext, LearningTarget, ReadingContext } from '../../api/types'
import { workbenchStore } from '../../store/workbenchStore'
import { projectStore } from '../../store/projectStore'
import type { RightPanel } from '../../store/types'

type SourceLocation = { path: string; lineno: number; target?: CodeReadingContext | null; source_kind?: 'workspace' | 'index' | null; content_sha256?: string | null; head_commit?: string | null; index_epoch?: number | null }

/** 来源只能使用对象自带身份；旧记录缺版本时等待用户主动打开当前文件。 */
export function sourceTarget(source: SourceLocation, projectId = projectStore.getState().currentProjectId): CodeReadingContext | null {
  if (projectId === null) return null
  if (source.target) return source.target.project_id === projectId ? source.target : null
  if (source.source_kind === 'workspace' ? !source.content_sha256 : !source.head_commit && source.index_epoch == null) return null
  return { kind: 'code', project_id: projectId, path: source.path, lineno: source.lineno,
    source_kind: source.source_kind ?? 'index', content_sha256: source.content_sha256 ?? undefined,
    head_commit: source.head_commit, index_epoch: source.index_epoch ?? undefined }
}

export function sourcePanel(source: SourceLocation): RightPanel {
  const target = sourceTarget(source)
  return target ? { mode: 'file', path: target.path, lineno: target.lineno, version: target.head_commit ?? undefined, indexEpoch: target.index_epoch, sourceKind: target.source_kind, contentSha: target.content_sha256 }
    : { mode: 'file', path: source.path, lineno: source.lineno, versionMissing: true }
}

export function openSource(source: SourceLocation) {
  if (source.target && source.target.project_id !== projectStore.getState().currentProjectId) return
  workbenchStore.getState().openMaterial(sourcePanel(source))
}

export function openCode(target: CodeReadingContext) {
  if (target.project_id !== projectStore.getState().currentProjectId) return
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
