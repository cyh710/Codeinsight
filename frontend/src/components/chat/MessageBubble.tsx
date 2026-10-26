/**
 * 消息气泡。用户消息是普通气泡；assistant 消息按 ADR 0007 分栏：
 * 正文（markdown）→ 工具时间线 → **事实**（每条带 file:line）→ **推断**
 * （带置信度）。核查信息按需展开，正文始终可读。
 */
import { memo, useState } from 'react'
import { chatStore } from '../../store/chatStore'
import LearningMarkdown from '../learning/LearningMarkdown'
import { workbenchStore } from '../../store/workbenchStore'
import { AlertTriangle, CheckCircle2, Copy, Hourglass, Loader2, MoreHorizontal, Wrench } from 'lucide-react'
import type { ChatMessage } from '../../store/types'
import type { Citation, Inference } from '../../api/types'
import ConfirmDialog from '../common/ConfirmDialog'
import ActionMenu from '../common/ActionMenu'
import { useStore } from 'zustand'
import { projectStore } from '../../store/projectStore'
import ExplorationActions from '../exploration/ExplorationActions'
import ExplorationFlow from '../exploration/ExplorationFlow'
import { openRelated } from '../exploration/actions'
import { AnswerReviewDetails, AnswerReviewNotice } from './AnswerReview'

function CitationLine({ citation, onOpen }: { citation: Citation; onOpen: (c: Citation) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(citation)}
      className="mt-0.5 shrink-0 rounded bg-accent-soft/70 px-1.5 py-px font-mono text-[10px] text-accent transition-colors hover:bg-accent-soft"
      title="点击在右栏查看"
    >
      {citation.path}:{citation.lineno}
    </button>
  )
}

function FactList({
  facts,
  onOpenCitation,
}: {
  facts: NonNullable<ChatMessage['facts']>
  onOpenCitation: (c: Citation) => void
}) {
  return (
    <details className="mt-2 rounded-lg border border-slate-200/70 px-3 py-2" aria-label="事实">
      <summary className="cursor-pointer text-[11px] text-slate-500">
        代码事实 · {facts.length} 条
      </summary>
      <ul className="mt-3 space-y-1.5">
        {facts.map((fact, i) => (
          <li
            key={i}
            className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-xs leading-relaxed text-slate-700"
          >
            <CitationLine citation={fact.citation} onOpen={onOpenCitation} />
            <span className="min-w-0">{fact.text}</span>
          </li>
        ))}
      </ul>
    </details>
  )
}

function InferenceList({ inferences }: { inferences: Inference[] }) {
  return (
    <details className="mt-2 rounded-lg border border-slate-200/70 px-3 py-2" aria-label="推断">
      <summary className="cursor-pointer text-[11px] text-slate-500">
        推断（待核对） · {inferences.length} 条
      </summary>
      <ul className="mt-3 space-y-1.5">
        {inferences.map((inf, i) => (
          <li key={i} className="flex items-start gap-2 text-xs leading-relaxed text-slate-600">
            <span className="shrink-0 rounded bg-warning/10 px-1 py-px font-mono text-[10px] text-warning">
              {Math.round(inf.confidence * 100)}%
            </span>
            <span className="min-w-0">{inf.text}</span>
          </li>
        ))}
      </ul>
    </details>
  )
}

function ToolTimeline({ tools }: { tools: NonNullable<ChatMessage['tools']> }) {
  const rows = (
    <div className="mt-2 space-y-1" aria-label="工具调用">
      {tools.map((t, i) => (
        <div
          key={`${t.name}:${i}`}
          className="flex items-center gap-1.5 text-[11px] text-slate-500"
        >
          {t.status === 'running' ? (
            <Loader2 size={11} strokeWidth={1.8} className="shrink-0 animate-spin text-accent" />
          ) : t.status === 'ok' ? (
            <CheckCircle2 size={11} strokeWidth={1.8} className="shrink-0 text-success" />
          ) : (
            <AlertTriangle size={11} strokeWidth={1.8} className="shrink-0 text-danger" />
          )}
          <Wrench size={10} strokeWidth={1.8} className="shrink-0 text-slate-400" />
          <span>{({ search_code: '查找代码', read_file: '读取源码', find_symbol: '定位函数', search_knowledge: '查找教材', read_knowledge: '读取教材', get_callers: '查找调用者', get_callees: '查找被调用者' } as Record<string, string>)[t.name] ?? '核对项目资料'}</span>
          <details><summary className="cursor-pointer text-[10px]">细节</summary><span className="font-mono">{t.name}</span></details>
          <span className="truncate text-slate-400">{t.summary}</span>
        </div>
      ))}
    </div>
  )
  if (tools.some(tool => tool.status === 'running')) return rows
  return <details className="mt-2 text-xs text-slate-500"><summary className="cursor-pointer py-1">查阅过程 · {tools.length} 步{tools.some(tool => tool.status !== 'ok') ? ' · 有失败项' : ''}</summary>{rows}</details>
}

export interface MessageBubbleProps {
  message: ChatMessage
  onOpenCitation: (citation: Citation) => void
}

function MessageActions({ message }: { message: ChatMessage }) {
  const [copied, setCopied] = useState('复制回答')
  const [confirmRestore, setConfirmRestore] = useState(false)
  const restore = () => {
    const state = chatStore.getState()
    const original = state.messages.find(item => item.role === 'user' && item.requestId === message.requestId)
    if (!original) return
    if (state.draft.trim() && state.draft !== original.text) setConfirmRestore(true)
    else state.restoreQuestion(message)
  }
  return <><div className="message-actions">
    <button type="button" className="wb-icon-button" aria-label="复制回答" title={copied} onClick={() => { void navigator.clipboard.writeText(message.text).then(() => setCopied('已复制'), () => setCopied('复制失败，请手动选择文字')) }}><Copy size={15} /></button>
    {copied !== '复制回答' && <span role="status">{copied}</span>}
    {message.requestId && <ActionMenu label="回答操作" trigger={<MoreHorizontal size={17} />}>
      {close => <button role="menuitem" onClick={() => { close(); restore() }}>恢复问题到草稿</button>}
    </ActionMenu>}
    {message.legacy && <span title="这份旧记录未保存完整的来源和版本">旧记录</span>}
  </div><ConfirmDialog open={confirmRestore} title="替换当前草稿？" message="恢复这个问题会替换你正在写的内容。"
    confirmLabel="替换草稿" cancelLabel="保留草稿" onCancel={() => setConfirmRestore(false)}
    onConfirm={() => { chatStore.getState().restoreQuestion(message); setConfirmRestore(false) }} /></>
}

const MessageBubble = memo(function MessageBubble({ message, onOpenCitation: originalOpen }: MessageBubbleProps) {
  const detail = useStore(projectStore, s => s.currentDetail)
  const pid = useStore(projectStore, s => s.currentProjectId)
  const cid = useStore(chatStore, s => s.conversationId)
  const onOpenCitation = (citation: Citation) => originalOpen({ ...citation, head_commit: message.sourceHeadCommit ?? citation.head_commit })
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-[var(--chat-bubble-user-background)] px-3.5 py-2 text-sm leading-relaxed text-white shadow-sm">
          {message.text}
          {message.readingContext && <details className="mt-2 text-[10px] opacity-80"><summary className="cursor-pointer">本次提问的关联材料</summary><p>{message.readingContext.kind === 'code' ? `${message.readingContext.path}:${message.readingContext.lineno}` : `${message.readingContext.title ?? message.readingContext.topic_id} · ${message.readingContext.section_title ?? message.readingContext.section_id ?? ''}`}</p>{message.readingContext.preview && <p className="mt-1 whitespace-pre-wrap">{message.readingContext.preview}</p>}</details>}
        </div>
      </div>
    )
  }

  if (message.error && !message.text) {
    return (
      <div className="flex justify-start">
        <div
          className="max-w-[85%] rounded-2xl rounded-bl-md border border-danger/30 bg-danger-soft/40 px-3.5 py-2.5"
          role="alert"
        >
          <div className="flex items-center gap-1.5 text-xs font-semibold text-danger">
            <AlertTriangle size={13} strokeWidth={1.8} />
            {message.error.title}
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-slate-600">{message.error.hint}</p>
          <MessageActions message={message} />
        </div>
      </div>
    )
  }

  const settled = !message.streaming
  return (
    <div className="flex justify-start">
      <div className="assistant-answer min-w-0 max-w-full">
        <AnswerReviewNotice message={message} />
        <div
          className={`text-sm leading-relaxed text-slate-800 ${message.streaming ? 'reply-text-in' : settled ? 'reply-settled' : ''}`}
        >
          <LearningMarkdown
            text={message.text}
            targets={message.learningTargets}
            streaming={message.streaming}
            citations={message.exploration ? message.citations : undefined}
            onCitation={onOpenCitation}
            onKnowledge={message.exploration && message.citations?.length && pid !== null && message.requestId ? target => openRelated(target, pid, cid, message.requestId) : undefined}
          />
          {message.streaming && (
            <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-accent/60 align-middle" />
          )}
        </div>
        {message.knowledgeError && (
          <p
            role="status"
            className="mt-2 rounded-lg bg-warning/10 p-2 text-[11px] leading-6 text-warning"
          >
            {message.knowledgeError}
          </p>
        )}
        {message.error && message.text && (
          <p role="status" className="mt-2 text-xs leading-6 text-warning">
            {message.error.title} · {message.error.hint}
          </p>
        )}
        {!message.streaming && message.exploration && <>
          <ExplorationFlow flow={message.exploration.flow} stale={Boolean(detail && (detail.head_commit !== message.exploration.head_commit || detail.index_epoch !== message.exploration.index_epoch))} />
          <ExplorationActions actions={message.exploration.actions} version={message.exploration} requestId={message.requestId} />
        </>}
        {!message.streaming && !message.exploration && message.learningEntries && message.learningEntries.length > 0 && (
          <nav aria-label="继续学习" className="mt-3 border-t border-slate-200/60 pt-3">
            <p className="mb-2 text-[10px] font-semibold text-slate-400">继续学习</p>
            <div className="flex flex-wrap gap-2">
              {message.learningEntries.slice(0, 3).map((t) => (
                <button
                  type="button"
                  key={t.href}
                  onClick={() => workbenchStore.getState().openKnowledge(t)}
                  className="rounded-lg bg-accent-soft/60 px-2 py-1 text-left text-[11px] leading-5 text-accent hover:bg-accent-soft"
                >
                  {t.title}
                </button>
              ))}
            </div>
          </nav>
        )}
        {message.streaming && message.tools && message.tools.length > 0 && <ToolTimeline tools={message.tools} />}
        {settled && <div className="answer-footer">
          <details className="answer-details">
            <summary>来源与核查</summary>
            <div className="answer-metadata">
              <button type="button" className="wb-button" onClick={() => workbenchStore.getState().openEvidence(message.id)}>查看来源</button>
              {message.knowledgeSources && message.knowledgeSources.length > 0 && (
                <details className="mt-2 text-[10px] leading-6 text-slate-400">
                  <summary className="cursor-pointer">
                    来自内置教材 · {new Set(message.knowledgeSources.map(s => s.target.topic_id)).size} 个主题
                  </summary>
                  {message.knowledgeSources.map(s => (
                    <button
                      type="button"
                      key={s.target.href}
                      onClick={() => message.exploration && message.citations?.length && pid !== null && message.requestId ? openRelated(s.target, pid, cid, message.requestId) : workbenchStore.getState().openKnowledge(s.target)}
                      className="block text-left text-accent hover:underline"
                    >
                      {s.target.title}
                      {s.target.section_title ? ` · ${s.target.section_title}` : ''}
                    </button>
                  ))}
                </details>
              )}
              {message.tools && message.tools.length > 0 && <ToolTimeline tools={message.tools} />}
              {message.facts && message.facts.length > 0 && (
                <FactList facts={message.facts} onOpenCitation={onOpenCitation} />
              )}
              {message.inferences && message.inferences.length > 0 && (
                <InferenceList inferences={message.inferences} />
              )}
              <AnswerReviewDetails message={message} />
            </div>
          </details>
          <MessageActions message={message} />
        </div>}
        {settled && message.incomplete && (
          // 未完成≠没找到（契约 §8.3 新增字段）：内容照常显示，追加提示条，
          // 不能和上面的 abstained 弃答卡合并成同一种提示。
          <p
            className="mt-2 flex items-start gap-1.5 rounded-lg bg-warning/10 px-2.5 py-1.5 text-[11px] leading-relaxed text-warning"
            role="status"
          >
            <Hourglass size={12} strokeWidth={1.8} className="mt-0.5 shrink-0" />
            回答未完成——模型轮次达到上限。已有的内容仍然可用；继续追问或换个问法可以推进。
          </p>
        )}
      </div>
    </div>
  )
})

export default MessageBubble
