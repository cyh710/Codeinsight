import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useStore } from 'zustand'
import type { ConversationTurn, KnowledgeTopic, LearningTarget } from '../../api/types'
import { getTurn } from '../../api/conversations'
import { getKnowledgeTopic } from '../../api/learning'
import { panelKey, workbenchStore } from '../../store/workbenchStore'
import { selectedKnowledge } from '../learning/selection'
import LearningMarkdown from '../learning/LearningMarkdown'
import { openCode } from './actions'
import { chatStore } from '../../store/chatStore'
import { viewStore } from '../../store/viewStore'
import { layoutStore } from '../../store/layoutStore'
import { BookOpen, ChevronLeft } from 'lucide-react'

/** 解读绑定来源回合，正文仍从同版本教材读取；客户端缓存不授予事实资格。 */
export default function ContextReading({ projectId, conversationId, requestId, target }: {
  projectId: number; conversationId: string; requestId: string; target: LearningTarget
}) {
  const [state, setState] = useState<{ key: string; turn?: ConversationTurn; topic?: KnowledgeTopic; error?: string }>()
  const [selectionError, setSelectionError] = useState('')
  const [retry, setRetry] = useState(0)
  const readingMode = useStore(workbenchStore, s => s.readingMode)
  const root = useRef<HTMLElement>(null)
  const key = `${projectId}:${conversationId}:${requestId}:${target.topic_id}:${target.version}`
  useEffect(() => {
    let alive = true
    Promise.all([getTurn(projectId, conversationId, requestId), getKnowledgeTopic(target.topic_id)])
      .then(([turn, topic]) => { if (alive) setState({ key, turn, topic }) })
      .catch(error => { if (alive) setState({ key, error: String(error) }) })
    return () => { alive = false }
  }, [key, projectId, conversationId, requestId, target.topic_id, retry])
  const current = state?.key === key ? state : undefined
  const topic = current?.topic, turn = current?.turn
  const source = turn?.answer.knowledge_sources?.find(s => s.target.topic_id === target.topic_id && s.target.version === target.version)
  const sectionId = target.section_id ?? source?.target.section_id ?? topic?.sections[0]?.id
  useLayoutEffect(() => {
    if (!topic || topic.version !== target.version) return
    workbenchStore.getState().setReading({ kind: 'knowledge', topic_id: topic.id, version: topic.version,
      section_id: sectionId, title: topic.title, section_title: topic.sections.find(s => s.id === sectionId)?.title })
    const scroll = root.current?.closest('[data-reading-scroll]')
    if (scroll) scroll.scrollTop = workbenchStore.getState().scrollPositions[panelKey(workbenchStore.getState().rightPanel)] ?? 0
  }, [topic, target.version, sectionId, readingMode])
  if (!current) return <p role="status">恢复这次问题的解读与资料…</p>
  if (current.error) return <div role="alert">无法恢复来源回答：{current.error}<button className="wb-button" onClick={() => setRetry(n => n + 1)}>重试</button><button className="wb-button" onClick={() => workbenchStore.getState().openKnowledge(target)}>打开教材</button></div>
  if (!topic || !turn) return null
  const full = () => workbenchStore.getState().openKnowledge({ ...target, version: topic.version, title: topic.title })
  if (topic.version !== target.version || !topic.sections.some(s => s.id === sectionId)) return <div role="alert">原章节已更新，原提问关联保持不变。<button className="wb-button" onClick={full}>打开当前教材</button></div>
  const citations = turn.answer.citations ?? []
  const associated = [...(turn.answer.knowledge_sources?.map(s => s.target) ?? []), ...(turn.answer.learning_targets ?? []),
    ...(turn.answer.exploration?.actions.flatMap(a => a.kind === 'knowledge' && a.target?.kind === 'knowledge' ? [a.target] : []) ?? [])]
  if (!associated.some(t => t.topic_id === target.topic_id && t.version === target.version)) return <div role="alert">原回答没有关联这个知识目标。<button className="wb-button" onClick={full}>打开教材全文</button></div>
  const takeaways = turn.answer.exploration?.takeaways ?? []
  return <article ref={root} className="context-reading" data-reading-ready="true">
    <header><h2>{topic.title}</h2></header>
    <div className="context-reading-tools context-reading-actions"><button className="context-reading-primary" type="button" onClick={full}><BookOpen size={18} aria-hidden="true" />阅读全文</button><button className="context-reading-return" type="button" onClick={() => { void chatStore.getState().openConversation(projectId, conversationId, requestId).then(() => { viewStore.getState().setCenterTab('chat'); layoutStore.setState({ full: false, ...(layoutStore.getState().viewport < 1100 ? { right: false } : {}) }) }) }}><ChevronLeft size={16} aria-hidden="true" />回到来源回答</button></div>
    {(citations.length > 0 || takeaways.length > 0) && <div className="context-project-link">
      {takeaways.length > 0 && <div className="context-excerpt"><LearningMarkdown text={takeaways.slice(0, 1).join('\n\n')} citations={citations} onCitation={c => openCode({ kind: 'code', project_id: projectId, path: c.path, lineno: c.lineno, head_commit: turn.answer.source_head_commit, index_epoch: turn.answer.evidence_review?.source_version?.index_epoch })} /></div>}
      {citations.length > 0 && <div className="context-project-sources"><button type="button" title={citations[0].path} onClick={() => openCode({ kind: 'code', project_id: projectId, path: citations[0].path, lineno: citations[0].lineno, head_commit: turn.answer.source_head_commit, index_epoch: turn.answer.evidence_review?.source_version?.index_epoch })}>{citations[0].path}:{citations[0].lineno}</button>
        {citations.length > 1 && <details><summary>另 {citations.length - 1} 处来源</summary>{citations.slice(1).map(c => <button type="button" className="block text-left" key={`${c.path}:${c.lineno}`} onClick={() => openCode({ kind: 'code', project_id: projectId, path: c.path, lineno: c.lineno, head_commit: turn.answer.source_head_commit, index_epoch: turn.answer.evidence_review?.source_version?.index_epoch })}>{c.path}:{c.lineno}</button>)}</details>}
      </div>}
    </div>}
    <div className="context-reading-tools"><button type="button" onPointerDown={e => e.preventDefault()} onClick={() => {
      try { workbenchStore.getState().fixReading(selectedKnowledge(root.current!, topic)); setSelectionError(''); viewStore.getState().setCenterTab('chat'); layoutStore.setState({ full: false, ...(layoutStore.getState().viewport < 1100 ? { right: false } : {}) }); requestAnimationFrame(() => document.querySelector<HTMLTextAreaElement>('.wb-center textarea')?.focus()) } catch (e) { setSelectionError(String(e)) }
    }}>问选中段落</button></div>
    {selectionError && <p role="alert">{selectionError}</p>}
    {topic.sections.filter(s => s.id === sectionId).map(s => <section key={s.id} data-section-id={s.id}><h3>{s.title}</h3><LearningMarkdown text={s.content} targets={topic.learning_targets} assets={topic.assets} selectable /></section>)}
    <details><summary>本章来源</summary>{topic.sources.map(s => <p key={s.id}><a href={s.url} target="_blank" rel="noreferrer">{s.title}</a> · {s.license}</p>)}</details>
  </article>
}
