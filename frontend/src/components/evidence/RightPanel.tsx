/**
 * 右栏：按 `workbenchStore.rightPanel` 三态切换——
 * 证据面板（默认）/ 符号详情 / 概念卡。后两者**替换**整个右栏
 * （C-Q3 已对齐：不弹层，弹层会挡住证据），返回证据是显式按钮。
 */
import { useStore } from 'zustand'
import { ArrowLeft } from 'lucide-react'
import { workbenchStore } from '../../store/workbenchStore'
import EvidenceList from './EvidenceList'
import SymbolDetailCard from './SymbolDetailCard'
import ConceptCard from '../concept/ConceptCard'

const PANEL_TITLE: Record<string, string> = {
  evidence: '证据',
  symbol: '符号',
  concept: '概念',
}

export default function RightPanel() {
  const rightPanel = useStore(workbenchStore, (s) => s.rightPanel)

  return (
    <aside className="flex h-full min-h-0 w-[26rem] shrink-0 flex-col border-l border-slate-200/80 bg-bg-elevated">
      <div className="flex items-center gap-2 border-b border-slate-200/70 px-3.5 py-2.5">
        {rightPanel.mode !== 'evidence' && (
          <button
            type="button"
            onClick={() => workbenchStore.getState().backToEvidence()}
            className="flex h-6 w-6 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-accent-soft hover:text-accent"
            title="返回证据面板"
            aria-label="返回证据面板"
          >
            <ArrowLeft size={14} strokeWidth={1.8} />
          </button>
        )}
        <h2 className="text-xs font-semibold tracking-wide text-slate-500">
          {PANEL_TITLE[rightPanel.mode]}
        </h2>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        {rightPanel.mode === 'evidence' && <EvidenceList />}
        {rightPanel.mode === 'symbol' && <SymbolDetailCard qualname={rightPanel.qualname} />}
        {rightPanel.mode === 'concept' && <ConceptCard conceptId={rightPanel.conceptId} />}
      </div>
    </aside>
  )
}
