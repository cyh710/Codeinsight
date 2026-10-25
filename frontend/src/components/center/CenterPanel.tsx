/**
 * 中栏：对话 / 关系图 / 变更时间线。
 *
 * 三屏共用一个标签栏，因为它们是「同一次探索」的三种视图：
 * 问出来的符号可以直接丢进关系图（右栏符号卡上的按钮），
 * 时间线里的变更又能点回文件与符号。
 */
import { useStore } from 'zustand'
import { History, MessageSquare, Share2 } from 'lucide-react'
import type { Citation } from '../../api/types'
import { viewStore, type CenterTab } from '../../store/viewStore'
import ChatWindow from '../chat/ChatWindow'
import GraphView from '../graph/GraphView'
import TimelineView from '../timeline/TimelineView'

const TABS: Array<{ id: CenterTab; label: string; icon: typeof MessageSquare }> = [
  { id: 'chat', label: '对话', icon: MessageSquare },
  { id: 'graph', label: '关系图', icon: Share2 },
  { id: 'timeline', label: '时间线', icon: History },
]

export function CenterNavigation() {
  const centerTab = useStore(viewStore, (s) => s.centerTab)

  return (
    <nav aria-label="工作台视图" className="flex items-center gap-1">
      {TABS.map(({ id, label, icon: Icon }) => {
        const active = centerTab === id
        return (
          <button
            key={id}
            type="button"
            onClick={() => viewStore.getState().setCenterTab(id)}
            aria-current={active ? 'page' : undefined}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs transition-colors ${
              active
                ? 'bg-accent-soft text-accent'
                : 'text-slate-500 hover:bg-slate-50 hover:text-slate-700'
            }`}
          >
            <Icon size={13} strokeWidth={1.8} />
            {label}
          </button>
        )
      })}
    </nav>
  )
}

export default function CenterPanel({ onOpenCitation }: { onOpenCitation: (c: Citation) => void }) {
  const centerTab = useStore(viewStore, (s) => s.centerTab)
  return (
    <section className="flex h-full min-h-0 min-w-0 flex-1 flex-col bg-bg">
      <div className="min-h-0 flex-1">
        {centerTab === 'chat' && <ChatWindow onOpenCitation={onOpenCitation} />}
        {centerTab === 'graph' && <GraphView />}
        {centerTab === 'timeline' && <TimelineView />}
      </div>
    </section>
  )
}
