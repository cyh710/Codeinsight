/**
 * 证据列表：取**最后一条 assistant 消息**的证据（含正在流的那条——
 * 边流边渲染是契约 §8.3 对 evidence 事件的设计意图）。
 * 每格保留位置、片段和概念入口；检索通道与分数按需展开。
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

function EvidenceCard({ item, version }: { item: PanelEvidence; version?: string | null }) {
  const open = () => {
    if (item.qualname) workbenchStore.getState().selectSymbol(item.qualname, item.path, item.lineno, version ?? '')
    else workbenchStore.getState().selectFile(item.path, item.lineno, version ?? '')
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
      </button>
      {item.qualname && (
        <p className="mt-1 truncate font-mono text-[10px] text-slate-400">{item.qualname}</p>
      )}
      {!version && <p className="mt-1 text-xs text-slate-500">原版本未记录，将打开当前索引。</p>}
      <pre className="mt-1.5 max-h-28 overflow-auto rounded-md bg-slate-50 px-2 py-1.5 font-mono text-[10.5px] leading-relaxed text-slate-600">
        {item.snippet}
      </pre>
      {item.concepts.length > 0 && (
        <div className="mt-1.5 flex flex-wrap items-center gap-1">
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
      {(item.lanes.length > 0 || item.score !== undefined) && <details className="evidence-technical">
        <summary>检索详情</summary>
        {item.score !== undefined && <p>检索分数 {item.score.toFixed(2)}</p>}
        <p>{item.lanes.map(lane => LANE_LABEL[lane] ?? lane).join(' · ')}</p>
      </details>}
    </article>
  )
}

export default function EvidenceList({ messageId }: { messageId?: string }) {
  const messages = useStore(chatStore, (s) => s.messages)
  const last = messageId ? messages.find(m => m.id === messageId) : [...messages].reverse().find((m) => m.role === 'assistant')
  const items = [...(last?.evidence ?? [])]
  for (const citation of last?.citations ?? []) {
    if (!items.some(item => item.path === citation.path && item.lineno === citation.lineno)) items.push({ ...citation, lanes: [], concepts: [] })
  }

  return (
    <div className="space-y-2">
      {last?.knowledgeSources?.map(hit => <article key={hit.target.href} className="rounded-xl border border-sky-100 bg-sky-50/40 p-3">
        <button className="text-left text-xs font-medium text-accent" onClick={() => workbenchStore.getState().openKnowledge(hit.target)}>教材 · {hit.target.title}{hit.target.section_title ? ` · ${hit.target.section_title}` : ''}</button>
        <p className="mt-1 line-clamp-3 text-xs leading-6 text-slate-500">{hit.summary || hit.snippet}</p>
      </article>)}
      {items.length === 0 ? !last?.knowledgeSources?.length && (
        <p className="px-1 py-6 text-center text-xs leading-relaxed text-slate-400">
          提问后，这里会显示找到的代码位置。
        </p>
      ) : (
        items.map((item, i) => <EvidenceCard key={`${item.path}:${item.lineno}:${i}`} item={item} version={last?.sourceHeadCommit ?? last?.citations?.find(c => c.path === item.path && c.lineno === item.lineno)?.head_commit} />)
      )}
    </div>
  )
}
