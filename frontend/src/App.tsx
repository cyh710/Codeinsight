/**
 * CodeInsight 工作台：三栏布局（规格 §3.4）。
 *
 * 左栏 文件/符号树 · 中栏 对话流（SSE）· 右栏 证据面板（可被符号详情/
 * 概念卡替换）。交互约定的细节见各栏组件头注释。
 */
import { useEffect, type CSSProperties } from 'react'
import { useStore } from 'zustand'
import { projectStore } from './store/projectStore'
import { workbenchStore } from './store/workbenchStore'
import { isMockMode } from './api/dataSource'
import type { Citation } from './api/types'
import LeftPanel from './components/tree/LeftPanel'
import CenterPanel, { CenterNavigation } from './components/center/CenterPanel'
import RightPanel from './components/evidence/RightPanel'
import { layoutStore } from './store/layoutStore'
import { chatStore } from './store/chatStore'
import { persistenceStore } from './store/persistence'
import { restoreLocation, startNavigation } from './store/navigation'
import SplitHandle from './components/common/SplitHandle'
import './workbench.css'
import './workbench-density.css'

// 引用点击 → 右栏符号详情（无 qualname 时退回文件选中）。
function openCitation(c: Citation) {
  if (c.qualname) workbenchStore.getState().selectSymbol(c.qualname, c.path, c.lineno, c.head_commit)
  else workbenchStore.getState().selectFile(c.path, c.lineno, c.head_commit)
}

let initialization: Promise<void> | undefined
export default function App() {
  const layout = useStore(layoutStore)
  const saving = useStore(persistenceStore)
  const newEvidence = useStore(workbenchStore, s => s.newEvidence)
  useEffect(() => {
    let alive = true, dispose: (() => void) | undefined
    initialization ??= projectStore.getState().init().then(restoreLocation)
    void initialization.then(() => { if (alive) dispose = startNavigation() })
    const resize = () => layoutStore.getState().setViewport(innerWidth)
    addEventListener('resize', resize)
    const timer = setInterval(() => { void chatStore.getState().refreshConversations(); void chatStore.getState().pollRunning() }, 2500)
    return () => { alive = false; dispose?.(); removeEventListener('resize', resize); clearInterval(timer) }
  }, [])
  const single = layout.full || layout.viewport < 1100
  const leftOverlay = single || layout.viewport - layout.leftWidth - (layout.right ? layout.rightWidth + 6 : 0) - 6 < 440
  const styles = { '--left-width': `${layout.leftWidth}px`, '--right-width': `${Math.min(layout.rightWidth, layout.viewport - (layout.left && !leftOverlay ? layout.leftWidth + 6 : 0) - 446)}px` } as CSSProperties
  const projectsError = useStore(projectStore, (s) => s.error)

  return (
    <div className="wb-app flex h-screen flex-col overflow-hidden bg-bg text-slate-800" style={styles}>
      <header className="workbench-header shrink-0 border-b border-slate-200/80 bg-bg-elevated">
        <div className="flex min-w-0 items-center gap-3">
          <h1 className="text-sm font-semibold tracking-tight text-slate-700">CodeInsight</h1>
          <button type="button" className="wb-button" aria-expanded={layout.left} aria-controls="workspace-left" onClick={layout.toggleLeft}>项目与对话</button>
        </div>
        <CenterNavigation />
        <div className="flex min-w-0 items-center justify-end gap-2">
          <button data-material-toggle type="button" className="wb-button" aria-expanded={layout.right} aria-controls="workspace-materials" onClick={layout.toggleRight}>{layout.right ? '隐藏材料' : '打开材料'}{newEvidence ? ' · 有新来源' : ''}</button>
          <button type="button" className="wb-button" onClick={layout.reset}>恢复布局</button>
          {isMockMode && (
            <span
              className="rounded bg-warning/10 px-1.5 py-px text-[10px] text-warning"
              title="当前使用真实索引快照回放（VITE_CI_MOCK=0 切换真实后端）"
            >
              mock 快照模式
            </span>
          )}
          {projectsError && (
            <span className="truncate text-[11px] text-danger" role="alert" title={projectsError}>
              {projectsError}
            </span>
          )}
        </div>
      </header>

      {saving.error && <p role="alert" className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800">{saving.error}</p>}
      <main className={`wb-main ${single ? 'wb-single' : ''} ${layout.full ? 'wb-full' : ''}`}>
        <div id="workspace-left" className={`wb-left ${!layout.left || layout.full ? 'wb-hidden' : ''} ${leftOverlay ? 'wb-overlay' : ''}`}>
          <LeftPanel />
        </div>
        <SplitHandle side="left" overlay={leftOverlay} />
        {layout.left && leftOverlay && !layout.full && <button type="button" aria-label="关闭项目侧栏" className="wb-scrim" onClick={layout.toggleLeft} />}
        <div className={`wb-center ${single && layout.right ? 'wb-hidden' : ''}`}>
          <CenterPanel onOpenCitation={openCitation} />
        </div>
        <SplitHandle side="right" overlay={single} />
        <div id="workspace-materials" className={`wb-materials ${!layout.right ? 'wb-hidden' : ''}`}>
          <RightPanel />
        </div>
      </main>
      <footer className="wb-status"><span>{saving.pending ? '正在保存工作区…' : saving.error ? '本地保存异常' : '已自动保存'}</span></footer>
    </div>
  )
}
