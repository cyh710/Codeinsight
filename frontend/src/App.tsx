/**
 * CodeInsight 工作台：三栏布局（规格 §3.4）。
 *
 * 左栏 文件/符号树 · 中栏 对话流（SSE）· 右栏 证据面板（可被符号详情/
 * 概念卡替换）。交互约定的细节见各栏组件头注释。
 */
import { useEffect, type CSSProperties } from 'react'
import { useStore } from 'zustand'
import { Loader2 } from 'lucide-react'
import { projectStore } from './store/projectStore'
import { workbenchStore } from './store/workbenchStore'
import { isMockMode } from './api/dataSource'
import { openSource } from './components/exploration/actions'
import LeftPanel from './components/tree/LeftPanel'
import CenterPanel, { CenterNavigation } from './components/center/CenterPanel'
import RightPanel from './components/evidence/RightPanel'
import { layoutStore } from './store/layoutStore'
import { chatStore } from './store/chatStore'
import { persistenceStore } from './store/persistence'
import { restoreLocation, startNavigation } from './store/navigation'
import SplitHandle from './components/common/SplitHandle'
import WorkspacePanel from './components/common/WorkspacePanel'
import ProjectIndexNotice from './components/tree/ProjectIndexNotice'
import BackendVersionNotice from './components/common/BackendVersionNotice'
import './workbench.css'
import './workbench-density.css'
import './workbench-motion.css'
import './components/exploration/exploration.css'
import './sidebar.css'

const openCitation = openSource

let initialization: Promise<void> | undefined
const SPLIT_WIDTH = 1
export default function App() {
  const layout = useStore(layoutStore)
  const saving = useStore(persistenceStore)
  const newEvidence = useStore(workbenchStore, s => s.newEvidence)
  useEffect(() => {
    let alive = true, dispose: (() => void) | undefined
    // 热更新已有工作台时沿用当前身份，避免重新激活会话或擅自展开已隐藏的材料。
    initialization ??= projectStore.getState().currentProjectId !== null && projectStore.getState().projects.length > 0
      ? Promise.resolve()
      : projectStore.getState().init().then(restoreLocation)
    void initialization.then(() => { if (alive) dispose = startNavigation() })
    const resize = () => layoutStore.getState().setViewport(innerWidth)
    addEventListener('resize', resize)
    const timer = setInterval(() => { void chatStore.getState().refreshConversations(); void chatStore.getState().pollRunning() }, 2500)
    return () => { alive = false; dispose?.(); removeEventListener('resize', resize); clearInterval(timer) }
  }, [])
  const single = layout.full || layout.viewport < 1100
  const leftOverlay = single || layout.viewport - layout.leftWidth - (layout.right ? layout.rightWidth + SPLIT_WIDTH : 0) - SPLIT_WIDTH < 440
  const styles = { '--split-width': `${SPLIT_WIDTH}px`, '--left-width': `${layout.leftWidth}px`, '--right-width': `${Math.min(layout.rightWidth, layout.viewport - (layout.left && !leftOverlay ? layout.leftWidth + SPLIT_WIDTH : 0) - 440 - SPLIT_WIDTH)}px` } as CSSProperties
  const projectsError = useStore(projectStore, (s) => s.error)

  return (
    <div className="wb-app flex h-screen flex-col overflow-hidden bg-bg text-slate-800" style={styles} data-resizing={layout.resizing || undefined}>
      <BackendVersionNotice />
      <header className="workbench-header shrink-0 border-b border-slate-200/80 bg-bg-elevated">
        <div className="flex min-w-0 items-center gap-3">
          <h1 className="text-sm font-semibold tracking-tight text-slate-700">CodeInsight</h1>
          <button type="button" className="wb-button" aria-expanded={layout.left} aria-controls="workspace-left" onClick={layout.toggleLeft}>项目与对话</button>
        </div>
        <CenterNavigation />
        <div className="flex min-w-0 items-center justify-end gap-2">
          <span className="workspace-save-slot">{saving.pending > 0 && !saving.error && <span role="status" aria-label="正在保存工作区…" title="正在保存工作区…"><Loader2 size={14} className="animate-spin" /></span>}</span>
          <button data-material-toggle type="button" className="wb-button" aria-expanded={layout.right} aria-controls="workspace-materials" onClick={layout.toggleRight}>{layout.right ? '隐藏材料' : '打开材料'}{newEvidence && !layout.right ? ' · 有新来源' : ''}</button>
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
      <ProjectIndexNotice />
      <main className={`wb-main ${single ? 'wb-single' : ''} ${layout.full ? 'wb-full' : ''}`}>
        <WorkspacePanel id="workspace-left" side="left" open={layout.left && !layout.full} overlay={leftOverlay}>
          <LeftPanel />
        </WorkspacePanel>
        <SplitHandle side="left" overlay={leftOverlay} />
        {layout.left && leftOverlay && !layout.full && !(single && layout.right) && <button type="button" aria-label="关闭项目侧栏" className="wb-scrim" style={layout.right ? { right: 'calc(var(--right-width) + var(--split-width))' } : undefined} onClick={layout.toggleLeft} />}
        <div className={`wb-center ${single && layout.right ? 'wb-hidden' : ''}`}>
          <CenterPanel onOpenCitation={openCitation} />
        </div>
        <SplitHandle side="right" overlay={single} />
        <WorkspacePanel id="workspace-materials" side="right" open={layout.right}>
          <RightPanel />
        </WorkspacePanel>
      </main>
    </div>
  )
}
