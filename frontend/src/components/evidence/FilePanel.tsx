import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useStore } from 'zustand'
import { readProjectCode } from '../../api/learning'
import { projectStore } from '../../store/projectStore'
import { panelKey, workbenchStore } from '../../store/workbenchStore'

export default function FilePanel({ path, lineno }: { path: string; lineno: number }) {
  const projectId = useStore(projectStore, (s) => s.currentProjectId)
  const [data, setData] = useState<{
    content: string
    start_line: number
    end_line: number
  } | null>(null)
  const [error, setError] = useState('')
  const root = useRef<HTMLElement>(null)
  useEffect(() => {
    if (projectId === null) return
    let alive = true
    readProjectCode(projectId, path, lineno)
      .then((r) => {
        if (alive) setData(r)
      })
      .catch((e) => {
        if (alive) setError(String(e))
      })
    return () => {
      alive = false
    }
  }, [projectId, path, lineno])
  useLayoutEffect(() => {
    if (!data || projectId === null) return
    workbenchStore
      .getState()
      .setReading({
        kind: 'code',
        project_id: projectId,
        path,
        lineno: data.start_line,
        end_lineno: data.end_line,
      })
    const scroll = root.current?.closest('[data-reading-scroll]') as HTMLElement | null
    if (scroll)
      scroll.scrollTop =
        workbenchStore.getState().scrollPositions[panelKey(workbenchStore.getState().rightPanel)] ??
        0
  }, [data, projectId, path])
  if (error)
    return (
      <p role="alert" className="text-xs text-danger">
        {error}
      </p>
    )
  if (!data) return <p className="text-xs text-slate-400">读取索引对应的代码…</p>
  return (
    <article ref={root} data-reading-ready className="space-y-3">
      <p className="break-all font-mono text-xs leading-6 text-slate-500">
        {path}:{data.start_line}–{data.end_line}
      </p>
      <pre className="overflow-x-auto rounded-lg bg-slate-50 p-3 text-[11px] leading-6 text-slate-700">
        {data.content.split('\n').map((line, i) => (
          <div key={i}>
            <span className="mr-3 inline-block w-8 select-none text-right text-slate-300">
              {data.start_line + i}
            </span>
            {line}
          </div>
        ))}
      </pre>
      <p className="text-[11px] leading-6 text-slate-400">
        当前窗口最多 200 行；可以结合这个代码位置继续提问。
      </p>
    </article>
  )
}
