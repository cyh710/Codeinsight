/**
 * CodeInsight 工作台：三栏布局（规格 §3.4）。
 *
 * 左栏 文件/符号树 · 中栏 对话流（SSE）· 右栏 证据面板（可被符号详情/
 * 概念卡替换）。交互约定的细节见各栏组件头注释。
 */
import { useEffect } from 'react'
import { useStore } from 'zustand'
import { projectStore } from './store/projectStore'
import { workbenchStore } from './store/workbenchStore'
import { isMockMode } from './api/dataSource'
import type { Citation } from './api/types'
import LeftPanel from './components/tree/LeftPanel'
import CenterPanel from './components/center/CenterPanel'
import RightPanel from './components/evidence/RightPanel'
import { getKnowledgeTopic } from './api/learning'

// 引用点击 → 右栏符号详情（无 qualname 时退回文件选中）。
function openCitation(c: Citation) {
  if (c.qualname) workbenchStore.getState().selectSymbol(c.qualname, c.path, c.lineno)
  else workbenchStore.getState().selectFile(c.path, c.lineno)
}

export default function App() {
  const initProject = projectStore.getState().init
  useEffect(() => {
    let alive = true
    void initProject().then(async () => {
      const match = /^\/learn\/([a-z][a-z0-9-]*)$/.exec(window.location.pathname)
      if (!match) return
      try {
        const topic = await getKnowledgeTopic(match[1])
        if (alive)
          workbenchStore
            .getState()
            .openKnowledge({
              topic_id: topic.id,
              title: topic.title,
              version: topic.version,
              section_id: window.location.hash.slice(1) || null,
              href: window.location.pathname + window.location.hash,
            })
      } catch {
        if (alive) workbenchStore.getState().openKnowledgeTree()
      }
    })
    return () => {
      alive = false
    }
  }, [initProject])

  const projectsError = useStore(projectStore, (s) => s.error)

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-bg text-slate-800">
      <header className="flex shrink-0 items-center gap-3 border-b border-slate-200/80 bg-bg-elevated px-4 py-2">
        <h1 className="text-sm font-semibold tracking-tight text-slate-700">CodeInsight</h1>
        <span className="text-[10px] text-slate-400">代码理解工作台</span>
        {isMockMode && (
          <span
            className="rounded bg-warning/10 px-1.5 py-px text-[10px] text-warning"
            title="当前使用真实索引快照回放（VITE_CI_MOCK=0 切换真实后端）"
          >
            mock 快照模式
          </span>
        )}
        {projectsError && (
          <span className="ml-auto text-[11px] text-danger" role="alert">
            {projectsError}
          </span>
        )}
      </header>

      <main className="flex min-h-0 flex-1">
        <LeftPanel />
        <CenterPanel onOpenCitation={openCitation} />
        <RightPanel />
      </main>
    </div>
  )
}
