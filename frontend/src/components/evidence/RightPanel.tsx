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
import { layoutStore } from '../../store/layoutStore'
import { viewStore } from '../../store/viewStore'

// 右栏标题给用户看，不是给开发者看——「符号」「工程概念」这类内部术语
// 用户读不懂，标题要说清楚这里是什么。
const titles: Record<string, string> = {
  evidence: '找到的代码',
  symbol: '代码位置',
  concept: '概念说明',
  file: '源码',
  knowledge: '教材',
  'knowledge-tree': '教材目录',
}

export default function RightPanel() {
  const state = useStore(workbenchStore)
  const full = useStore(layoutStore, s => s.full)
  const centerView = useStore(viewStore, s => s.centerTab)
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
    <aside className="flex h-full min-h-0 w-full shrink-0 flex-col border-l border-slate-200/80 bg-bg-elevated">
      <div className="flex flex-wrap items-center gap-1 border-b border-slate-200/70 px-3 py-2.5">
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
        <div className="ml-auto flex flex-wrap gap-2">
          <button type="button" className="wb-button" aria-pressed={state.pinned} onClick={() => state.setPinned(!state.pinned)}>{state.pinned ? '已固定' : '固定材料'}</button>
          <button type="button" className="wb-button" onClick={() => { if (layoutStore.getState().viewport < 1100) layoutStore.setState({ right: false, full: false }); else layoutStore.getState().toggleFull() }}>{full || layoutStore.getState().viewport < 1100 ? `回到${centerView === 'graph' ? '关系图' : centerView === 'timeline' ? '时间线' : '对话'}` : '展开阅读'}</button>
          <button type="button" aria-label="隐藏材料区域" className="wb-button" onClick={() => { layoutStore.setState({ right: false, full: false }); requestAnimationFrame(() => document.querySelector<HTMLButtonElement>('[data-material-toggle]')?.focus()) }}>关闭</button>
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
            教材目录
          </button>
        </div>
      </div>
      <div className="material-tabs">
        <div role="tablist" aria-label="阅读材料页签" className="flex min-w-0 flex-1 gap-1 overflow-x-auto">
          {state.tabs.map(tab => <div key={tab.id} className={`material-tab ${state.activeTab === tab.id ? 'active' : ''}`}>
            <button role="tab" aria-selected={state.activeTab === tab.id} title={`${tab.title}${tab.panel.mode === 'knowledge' ? ` · ${tab.panel.target.version}` : tab.panel.mode === 'file' || tab.panel.mode === 'symbol' ? ` · ${tab.panel.version ?? '当前版本'}` : ''}`} type="button" onClick={() => state.activateTab(tab.id)}
              onKeyDown={event => {
                const index = state.tabs.findIndex(item => item.id === tab.id)
                const next = event.key === 'ArrowRight' ? (index + 1) % state.tabs.length : event.key === 'ArrowLeft' ? (index + state.tabs.length - 1) % state.tabs.length : event.key === 'Home' ? 0 : event.key === 'End' ? state.tabs.length - 1 : null
                if (next !== null) { event.preventDefault(); state.activateTab(state.tabs[next].id); requestAnimationFrame(() => document.querySelectorAll<HTMLButtonElement>('[role="tablist"][aria-label="阅读材料页签"] [role="tab"]')[next]?.focus()) }
              }}>
              {tab.panel.mode === 'file' || tab.panel.mode === 'symbol' ? <Code2 aria-hidden="true" size={11} className="mr-1 inline" /> : tab.panel.mode === 'knowledge' ? <BookOpen aria-hidden="true" size={11} className="mr-1 inline" /> : null}
              {tab.title}
              {state.tabs.some(other => other.id !== tab.id && other.title === tab.title) && <span aria-hidden="true" className="ml-1 text-[9px] text-slate-400">{tab.panel.mode === 'knowledge' ? tab.panel.target.version.slice(0, 6) : tab.panel.mode === 'file' || tab.panel.mode === 'symbol' ? tab.panel.version?.slice(0, 6) : ''}</span>}
            </button>
            <button type="button" aria-label={`关闭页签 ${tab.title}`} onClick={() => state.closeTab(tab.id)}>×</button>
          </div>)}
        </div>
        <details className="relative shrink-0 text-xs"><summary className="wb-button cursor-pointer">材料操作</summary>
          <div className="absolute right-0 z-10 mt-1 w-52 space-y-1 rounded-lg border border-slate-200 bg-white p-2 shadow-lg">
            <button className="wb-button w-full" onClick={state.closeOtherTabs}>关闭其他页签</button>
            <button className="wb-button w-full" disabled={!state.closedTabs.length} onClick={state.reopenTab}>重新打开已关闭页签</button>
            <label className="flex items-center gap-2 p-2"><input type="checkbox" checked={state.followEvidence} onChange={e => state.setFollowEvidence(e.target.checked)} />跟随新的回答来源</label>
            {state.tabs.map(tab => <button key={tab.id} className="block w-full truncate px-2 py-1 text-left text-slate-500" onClick={() => state.activateTab(tab.id)}>{tab.title}</button>)}
          </div>
        </details>
      </div>
      {state.newEvidence && <button type="button" className="border-b border-sky-100 bg-sky-50 px-3 py-2 text-left text-xs text-accent" onClick={() => state.openEvidence()}>有新的回答来源，点击查看</button>}
      <div
        ref={scroll}
        data-reading-scroll
        onScroll={onScroll}
        className="min-h-0 flex-1 overflow-y-auto px-4 py-4"
      >
        <div key={key}>
          {panel.mode === 'evidence' && <EvidenceList messageId={panel.messageId} />}
          {panel.mode === 'symbol' && (
            <SymbolDetailCard qualname={panel.qualname} focusLine={panel.lineno} version={panel.version} />
          )}
          {panel.mode === 'concept' && <ConceptCard conceptId={panel.conceptId} />}
          {panel.mode === 'knowledge-tree' && <KnowledgeDirectory />}
          {panel.mode === 'knowledge' && <KnowledgeArticle target={panel.target} />}
          {panel.mode === 'file' && <FilePanel path={panel.path} lineno={panel.lineno} version={panel.version} />}
        </div>
      </div>
    </aside>
  )
}
