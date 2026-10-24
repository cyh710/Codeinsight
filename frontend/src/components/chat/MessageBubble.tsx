/**
 * 消息气泡。用户消息是普通气泡；assistant 消息按 ADR 0007 分栏：
 * 正文（markdown）→ 工具时间线 → **事实**（每条带 file:line）→ **推断**
 * （带置信度）。弃答时渲染弃答卡，不冒充有答案。
 */
import { memo } from 'react'
import Markdown from 'react-markdown'
import { AlertTriangle, Ban, CheckCircle2, Hourglass, Loader2, Wrench } from 'lucide-react'
import type { ChatMessage } from '../../store/types'
import type { Citation, Inference } from '../../api/types'

// remark 对中文相邻的 ** 粗体标记解析不良：插零宽空格帮它断词（抄织忆）。
function fixMarkdownBold(text: string): string {
  return text.replace(/(?<=[^\s*])\*\*/g, '​**').replace(/\*\*(?=[^\s*])/g, '**​')
}

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

function FactList({ facts, onOpenCitation }: {
  facts: NonNullable<ChatMessage['facts']>
  onOpenCitation: (c: Citation) => void
}) {
  return (
    <section className="mt-2 rounded-xl border border-success/25 bg-success/[0.04] px-3 py-2" aria-label="事实">
      <h4 className="text-[10px] font-semibold uppercase tracking-wider text-success">事实（带代码出处）</h4>
      <ul className="mt-1 space-y-1.5">
        {facts.map((fact, i) => (
          <li key={i} className="flex items-start gap-2 text-xs leading-relaxed text-slate-700">
            <CitationLine citation={fact.citation} onOpen={onOpenCitation} />
            <span className="min-w-0">{fact.text}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function InferenceList({ inferences }: { inferences: Inference[] }) {
  return (
    <section className="mt-2 rounded-xl border border-warning/25 bg-warning/[0.04] px-3 py-2" aria-label="推断">
      <h4 className="text-[10px] font-semibold uppercase tracking-wider text-warning">
        推断（模型判断，非代码事实）
      </h4>
      <ul className="mt-1 space-y-1.5">
        {inferences.map((inf, i) => (
          <li key={i} className="flex items-start gap-2 text-xs leading-relaxed text-slate-600">
            <span className="shrink-0 rounded bg-warning/10 px-1 py-px font-mono text-[10px] text-warning">
              {Math.round(inf.confidence * 100)}%
            </span>
            <span className="min-w-0">{inf.text}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function ToolTimeline({ tools }: { tools: NonNullable<ChatMessage['tools']> }) {
  return (
    <div className="mt-2 space-y-1" aria-label="工具调用">
      {tools.map((t, i) => (
        <div key={`${t.name}:${i}`} className="flex items-center gap-1.5 text-[11px] text-slate-500">
          {t.status === 'running' ? (
            <Loader2 size={11} strokeWidth={1.8} className="shrink-0 animate-spin text-accent" />
          ) : t.status === 'ok' ? (
            <CheckCircle2 size={11} strokeWidth={1.8} className="shrink-0 text-success" />
          ) : (
            <AlertTriangle size={11} strokeWidth={1.8} className="shrink-0 text-danger" />
          )}
          <Wrench size={10} strokeWidth={1.8} className="shrink-0 text-slate-400" />
          <span className="font-mono">{t.name}</span>
          <span className="truncate text-slate-400">{t.summary}</span>
        </div>
      ))}
    </div>
  )
}

export interface MessageBubbleProps {
  message: ChatMessage
  onOpenCitation: (citation: Citation) => void
}

const MessageBubble = memo(function MessageBubble({ message, onOpenCitation }: MessageBubbleProps) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-[var(--chat-bubble-user-background)] px-3.5 py-2 text-sm leading-relaxed text-white shadow-sm">
          {message.text}
        </div>
      </div>
    )
  }

  if (message.error && !message.text) {
    return (
      <div className="flex justify-start">
        <div className="max-w-[85%] rounded-2xl rounded-bl-md border border-danger/30 bg-danger-soft/40 px-3.5 py-2.5" role="alert">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-danger">
            <AlertTriangle size={13} strokeWidth={1.8} />
            {message.error.title}
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-slate-600">{message.error.hint}</p>
        </div>
      </div>
    )
  }

  if (message.abstained && !message.streaming) {
    // 弃答：明确说没找到，绝不编造 file:line（ADR 0007 / 契约 §8.1）。
    return (
      <div className="flex justify-start">
        <div className="max-w-[85%] rounded-2xl rounded-bl-md border border-slate-300/60 bg-slate-50 px-3.5 py-2.5">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-500">
            <Ban size={13} strokeWidth={1.8} />
            未找到相关代码
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
            {message.abstentionReason || '索引里没有命中这个问题对应的代码，换个问法或先重建索引。'}
          </p>
        </div>
      </div>
    )
  }

  const settled = !message.streaming
  return (
    <div className="flex justify-start">
      <div className="max-w-[92%] rounded-2xl rounded-bl-md border border-[var(--chat-bubble-border)] bg-[var(--chat-bubble-background)] px-3.5 py-2.5 shadow-[var(--chat-bubble-shadow)] backdrop-blur-[var(--chat-bubble-filter)]">
        <div
          className={`text-sm leading-relaxed text-slate-800 ${message.streaming ? 'reply-text-in' : settled ? 'reply-settled' : ''}`}
        >
          <Markdown>{fixMarkdownBold(message.text)}</Markdown>
          {message.streaming && (
            <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-accent/60 align-middle" />
          )}
        </div>
        {message.tools && message.tools.length > 0 && <ToolTimeline tools={message.tools} />}
        {message.facts && message.facts.length > 0 && (
          <FactList facts={message.facts} onOpenCitation={onOpenCitation} />
        )}
        {message.inferences && message.inferences.length > 0 && (
          <InferenceList inferences={message.inferences} />
        )}
        {settled && message.incomplete && (
          // 未完成≠没找到（契约 §8.3 新增字段）：内容照常显示，追加提示条，
          // 不能和上面的 abstained 弃答卡合并成同一种提示。
          <p className="mt-2 flex items-start gap-1.5 rounded-lg bg-warning/10 px-2.5 py-1.5 text-[11px] leading-relaxed text-warning" role="status">
            <Hourglass size={12} strokeWidth={1.8} className="mt-0.5 shrink-0" />
            回答未完成——模型轮次达到上限。已有的内容仍然可用；继续追问或换个问法可以推进。
          </p>
        )}
      </div>
    </div>
  )
})

export default MessageBubble
