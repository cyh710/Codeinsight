/** 证据、代码与知识共用右栏导航；滚动位置按来路保存。 */
import { useLayoutEffect, useRef } from 'react'
import { useStore } from 'zustand'
import { ArrowLeft, ArrowRight, BookOpen, Code2 } from 'lucide-react'
import { panelKey, workbenchStore } from '../../store/workbenchStore'
import EvidenceList from './EvidenceList'
import SymbolDetailCard from './SymbolDetailCard'
import ConceptCard from '../concept/ConceptCard'
import KnowledgeDirectory from '../learning/KnowledgeDirectory'
import KnowledgeArticle from '../learning/KnowledgeArticle'
import FilePanel from './FilePanel'

const titles: Record<string, string> = {
  evidence: '代码证据',
  symbol: '符号',
  concept: '工程概念',
  file: '代码',
  knowledge: '阅读',
  'knowledge-tree': '知识目录',
}

export default function RightPanel() {
  const panel = useStore(workbenchStore, (s) => s.rightPanel)
  const index = useStore(workbenchStore, (s) => s.historyIndex)
  const length = useStore(workbenchStore, (s) => s.history.length)
  const path = useStore(workbenchStore, (s) => s.selectedPath)
  const scroll = useRef<HTMLDivElement>(null)
  const key = panelKey(panel)
  useLayoutEffect(() => {
    if (scroll.current && !['knowledge', 'file', 'symbol'].includes(panel.mode)) {
      scroll.current.scrollTop = workbenchStore.getState().scrollPositions[key] ?? 0
    }
  }, [key, panel.mode])
  const onScroll = () => {
    const element = scroll.current
    if (!element) return
    if (
      ['knowledge', 'file', 'symbol', 'knowledge-tree'].includes(panel.mode) &&
      !element.querySelector('[data-reading-ready]')
    )
      return
    workbenchStore.getState().saveScroll(key, element.scrollTop)
    if (panel.mode === 'knowledge') {
      const sections = [...element.querySelectorAll<HTMLElement>('[data-section-id]')]
      const top = element.getBoundingClientRect().top + 60
      const section =
        sections.filter((s) => s.getBoundingClientRect().top <= top).at(-1) ?? sections[0]
      const reading = workbenchStore.getState().reading
      if (
        section &&
        reading?.kind === 'knowledge' &&
        reading.section_id !== section.dataset.sectionId
      ) {
        workbenchStore.getState().setReading({ ...reading, section_id: section.dataset.sectionId })
      }
    }
  }
  return (
    <aside className="flex h-full min-h-0 w-[26rem] shrink-0 flex-col border-l border-slate-200/80 bg-bg-elevated">
      <div className="flex items-center gap-1 border-b border-slate-200/70 px-3 py-2.5">
        <button
          aria-label="返回上一处"
          disabled={index <= 0}
          onClick={() => workbenchStore.getState().goBack()}
          className="rounded p-1 text-slate-400 hover:bg-accent-soft disabled:opacity-25"
        >
          <ArrowLeft size={14} />
        </button>
        <button
          aria-label="前往下一处"
          disabled={index >= length - 1}
          onClick={() => workbenchStore.getState().goForward()}
          className="rounded p-1 text-slate-400 hover:bg-accent-soft disabled:opacity-25"
        >
          <ArrowRight size={14} />
        </button>
        <h2 className="ml-1 text-xs font-semibold text-slate-500">{titles[panel.mode]}</h2>
        <div className="ml-auto flex gap-2">
          {['knowledge', 'knowledge-tree', 'concept'].includes(panel.mode) && path && (
            <button
              onClick={() => workbenchStore.getState().returnToCode()}
              className="flex items-center gap-1 text-[11px] text-slate-500 hover:text-accent"
            >
              <Code2 size={13} />
              回到代码
            </button>
          )}
          <button
            onClick={() => workbenchStore.getState().openKnowledgeTree()}
            className="flex items-center gap-1 rounded bg-accent-soft/50 px-2 py-1 text-[11px] text-accent"
          >
            <BookOpen size={13} />
            知识目录
          </button>
        </div>
      </div>
      <div
        ref={scroll}
        data-reading-scroll
        onScroll={onScroll}
        className="min-h-0 flex-1 overflow-y-auto px-4 py-4"
      >
        <div key={key}>
          {panel.mode === 'evidence' && <EvidenceList />}
          {panel.mode === 'symbol' && (
            <SymbolDetailCard qualname={panel.qualname} focusLine={panel.lineno} />
          )}
          {panel.mode === 'concept' && <ConceptCard conceptId={panel.conceptId} />}
          {panel.mode === 'knowledge-tree' && <KnowledgeDirectory />}
          {panel.mode === 'knowledge' && <KnowledgeArticle target={panel.target} />}
          {panel.mode === 'file' && <FilePanel path={panel.path} lineno={panel.lineno} />}
        </div>
      </div>
    </aside>
  )
}
