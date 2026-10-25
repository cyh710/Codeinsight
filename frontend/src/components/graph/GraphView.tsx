/** 默认围绕一个代码位置阅读；原画布保留为高级全图。 */
import { useMemo, useState } from 'react'
import { useStore } from 'zustand'
import { ArrowLeft, Network, Route } from 'lucide-react'
import { projectStore } from '../../store/projectStore'
import { viewStore } from '../../store/viewStore'
import { workbenchStore } from '../../store/workbenchStore'
import AdvancedGraphView, { SymbolSearch } from './AdvancedGraphView'
import ReadingGraphView from './ReadingGraphView'
import './readingGraph.css'

export default function GraphView() {
  const projectId = useStore(projectStore, (s) => s.currentProjectId)
  const externalFocus = useStore(viewStore, (s) => s.graphFocus)
  const request = useStore(viewStore, (s) => s.graphRequest)
  const [modeChoice, setModeChoice] = useState({ projectId, request, mode: 'reading' })
  const mode =
    modeChoice.projectId === projectId && modeChoice.request === request
      ? modeChoice.mode
      : 'reading'
  const initialFocus = useMemo(() => {
    const panel = workbenchStore.getState().rightPanel
    return externalFocus ?? (panel.mode === 'symbol' ? panel.qualname : null)
    // 点击邻居只打开详情，不应让整张关系图自动换中心。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [externalFocus, request, projectId])
  const [choice, setChoice] = useState<{
    projectId: number | null
    request: number
    external: string | null
    focus: string | null
  } | null>(null)
  const focus =
    choice?.projectId === projectId &&
    choice.request === request &&
    choice.external === externalFocus
      ? choice.focus
      : initialFocus
  const [history, setHistory] = useState<{ projectId: number | null; items: (string | null)[] }>({
    projectId,
    items: [],
  })
  const trail = history.projectId === projectId ? history.items : []
  const changeFocus = (next: string | null, remember = true) => {
    if (next === focus) return
    if (remember) setHistory({ projectId, items: [...trail, focus] })
    viewStore.getState().setGraphFocus(next)
    setChoice({ projectId, request, external: next, focus: next })
  }
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-slate-200/70 bg-bg-elevated px-4 py-2.5">
        <div className="flex gap-1 rounded-lg bg-slate-100/80 p-0.5" aria-label="关系图模式">
          {[
            { id: 'reading', label: '局部阅读', icon: Route },
            { id: 'advanced', label: '高级全图', icon: Network },
          ].map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              aria-pressed={mode === id}
              onClick={() => setModeChoice({ projectId, request, mode: id })}
              className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs ${mode === id ? 'bg-white text-accent shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
            >
              <Icon size={13} />
              {label}
            </button>
          ))}
        </div>
        {mode === 'reading' && projectId !== null && (
          <div className="ml-auto flex items-center gap-2">
            {trail.length > 0 && (
              <button
                type="button"
                aria-label="返回上一个关系中心"
                onClick={() => {
                  const previous = trail.at(-1) ?? null
                  setHistory({ projectId, items: trail.slice(0, -1) })
                  changeFocus(previous, false)
                }}
                className="rounded-md p-1.5 text-slate-500 hover:bg-accent-soft hover:text-accent"
              >
                <ArrowLeft size={14} />
              </button>
            )}
            <SymbolSearch projectId={projectId} onPick={changeFocus} />
          </div>
        )}
      </div>
      <div className="min-h-0 flex-1">
        {mode === 'advanced' ? (
          <AdvancedGraphView />
        ) : (
          <ReadingGraphView projectId={projectId} focus={focus} onFocus={changeFocus} />
        )}
      </div>
    </div>
  )
}
