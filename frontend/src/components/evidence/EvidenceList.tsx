/**
 * 证据列表：取**最后一条 assistant 消息**的证据（含正在流的那条——
 * 边流边渲染是契约 §8.3 对 evidence 事件的设计意图）。
 * 每格：file:line（点击看符号/文件）+ 片段 + 命中通道 chips + 概念 chips。
 */
import { useStore } from 'zustand'
import { FileCode2 } from 'lucide-react'
import { chatStore, } from '../../store/chatStore'
import { workbenchStore } from '../../store/workbenchStore'
import type { PanelEvidence } from '../../store/types'

const LANE_LABEL: Record<string, string> = {
  bm25: '关键词',
  dense: '向量',
  symbol: '符号',
  concept: '概念',
  neighbor: '邻域',
}

function EvidenceCard({ item }: { item: PanelEvidence }) {
  const open = () => {
    if (item.qualname) workbenchStore.getState().selectSymbol(item.qualname, item.path)
    else workbenchStore.getState().selectFile(item.path)
  }
  return (
    <article className="rounded-xl border border-slate-200 bg-white px-3 py-2.5">
      <button
        type="button"
        onClick={open}
        className="flex w-full items-center gap-1.5 text-left"
        title="查看定义与关系"
      >
        <FileCode2 size={13} strokeWidth={1.7} className="shrink-0 text-accent/70" />
        <span className="truncate font-mono text-[11px] font-medium text-accent">
          {item.path}:{item.lineno}
        </span>
        {item.score !== undefined && (
          <span className="ml-auto shrink-0 font-mono text-[10px] text-slate-400">
            {item.score.toFixed(2)}
          </span>
        )}
      </button>
      {item.qualname && (
        <p className="mt-1 truncate font-mono text-[10px] text-slate-400">{item.qualname}</p>
      )}
      <pre className="mt-1.5 max-h-28 overflow-auto rounded-md bg-slate-50 px-2 py-1.5 font-mono text-[10.5px] leading-relaxed text-slate-600">
        {item.snippet}
      </pre>
      {(item.lanes.length > 0 || item.concepts.length > 0) && (
        <div className="mt-1.5 flex flex-wrap items-center gap-1">
          {item.lanes.map((lane) => (
            <span key={lane} className="rounded bg-accent-soft/70 px-1.5 py-px text-[10px] text-accent">
              {LANE_LABEL[lane] ?? lane}
            </span>
          ))}
          {item.concepts.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => workbenchStore.getState().openConcept(c)}
              className="rounded bg-warning/10 px-1.5 py-px text-[10px] text-warning transition-colors hover:bg-warning/20"
              title="打开概念卡"
            >
              #{c}
            </button>
          ))}
        </div>
      )}
    </article>
  )
}

export default function EvidenceList() {
  const messages = useStore(chatStore, (s) => s.messages)
  const last = [...messages].reverse().find((m) => m.role === 'assistant')
  const items = last?.evidence ?? []

  return (
    <div className="space-y-2">
      {items.length === 0 ? (
        <p className="px-1 py-6 text-center text-xs leading-relaxed text-slate-400">
          还没有证据。
          <br />
          提问后，检索命中的代码位置会实时出现在这里。
        </p>
      ) : (
        items.map((item, i) => <EvidenceCard key={`${item.path}:${item.lineno}:${i}`} item={item} />)
      )}
    </div>
  )
}
