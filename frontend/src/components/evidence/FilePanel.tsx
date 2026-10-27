import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useStore } from 'zustand'
import { readProjectCode } from '../../api/learning'
import { ApiError } from '../../api/client'
import { projectStore } from '../../store/projectStore'
import { panelKey, workbenchStore } from '../../store/workbenchStore'
import { layoutStore } from '../../store/layoutStore'
import CodeViewer from './CodeViewer'
import type { CodeReadingContext } from '../../api/types'
import { viewStore } from '../../store/viewStore'

type CodeWindow = Awaited<ReturnType<typeof readProjectCode>>
export default function FilePanel({ path, lineno, version, indexEpoch, sourceKind, contentSha }: { path: string; lineno: number; version?: string; indexEpoch?: number; sourceKind?: 'workspace' | 'index'; contentSha?: string }) {
  const projectId = useStore(projectStore, s => s.currentProjectId)
  const readingMode = useStore(workbenchStore, s => s.readingMode)
  const identity = `${projectId}:${path}:${lineno}:${version}:${indexEpoch}:${sourceKind}:${contentSha}`
  const [loaded, setLoaded] = useState<{ identity: string; data: CodeWindow } | null>(null)
  const [failure, setFailure] = useState<{ identity: string; error: string } | null>(null)
  const data = loaded?.identity === identity ? loaded.data : null
  const error = failure?.identity === identity ? failure.error : ''
  const [jump, setJump] = useState(String(lineno)), [retry, setRetry] = useState(0)
  const [selection, setSelection] = useState<{ startLine: number; endLine: number; startColumn: number; endColumn: number; text: string } | null>(null)
  const root = useRef<HTMLElement>(null)
  useEffect(() => {
    if (projectId === null) return
    let alive = true
    readProjectCode(projectId, path, lineno, indexEpoch, version, sourceKind, contentSha).then(result => { if (alive) { setLoaded({ identity, data: result }); setFailure(null); setSelection(null); workbenchStore.getState().bindFileVersion(path, lineno, result.head_commit, result.index_epoch, result.source_kind, result.content_sha256) } }).catch(e => { if (alive) setFailure({ identity, error: e instanceof ApiError ? `${e.title}：${e.hint}` : String(e) }) })
    return () => { alive = false }
  }, [projectId, path, lineno, retry, identity, indexEpoch, version, sourceKind, contentSha])
  const stale = Boolean(data && version && data.head_commit !== version)
  useLayoutEffect(() => {
    if (!data || projectId === null || stale) return
    workbenchStore.getState().setReading({ kind: 'code', project_id: projectId, path,
      lineno: data.start_line, end_lineno: data.end_line, head_commit: data.head_commit, index_epoch: data.index_epoch, content_sha256: data.content_sha256, source_kind: data.source_kind })
  }, [data, projectId, path, stale, readingMode])
  useLayoutEffect(() => {
    if (!data) return
    const container = root.current?.closest('[data-reading-scroll]') as HTMLElement | null
    if (container) container.scrollTop = workbenchStore.getState().scrollPositions[panelKey(workbenchStore.getState().rightPanel)] ?? 0
  }, [data])
  const move = (line: number) => workbenchStore.getState().selectFile(path, Math.max(1, Math.min(data?.total_lines ?? line, line)), data?.head_commit ?? version, data?.index_epoch ?? indexEpoch, data?.source_kind ?? sourceKind, data?.content_sha256 ?? contentSha)
  if (error) return <div role="alert" className="text-xs leading-6 text-danger">{error}<p>可重新读取原版本，或主动打开当前文件。</p><button className="wb-button" onClick={() => setRetry(v => v + 1)}>重新读取</button><button className="wb-button ml-2" onClick={() => workbenchStore.getState().selectFile(path, lineno, null, undefined, 'workspace')}>查看当前文件</button></div>
  if (!data) return <p className="text-xs text-slate-400">读取文件…</p>
  if (stale) return <div role="alert" className="text-xs leading-6 text-amber-700">这个页签的源码版本已更新，原位置未被替换。<button className="wb-button ml-2" onClick={() => { workbenchStore.getState().setIndexVersion(data.head_commit); workbenchStore.getState().selectFile(path, lineno, data.head_commit, data.index_epoch) }}>打开当前版本</button></div>
  const ask = () => {
    if (!selection || projectId === null) return
    const context: CodeReadingContext = { kind: 'code', project_id: projectId, path, head_commit: data.head_commit, index_epoch: data.index_epoch, source_kind: data.source_kind,
      content_sha256: data.content_sha256, lineno: selection.startLine, end_lineno: selection.endLine,
      selection: { start_column: selection.startColumn, end_column: selection.endColumn }, preview: selection.text }
    workbenchStore.getState().fixReading(context)
    viewStore.getState().setCenterTab('chat')
    if (layoutStore.getState().viewport < 1100) layoutStore.setState({ right: false, full: false })
    else layoutStore.setState({ full: false })
    requestAnimationFrame(() => document.querySelector<HTMLTextAreaElement>('.wb-center textarea')?.focus())
  }
  return <article ref={root} data-reading-ready className="space-y-3">
    <header className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
      <span className="break-all font-mono">{path}</span><span>{data.start_line}–{data.end_line} / {data.total_lines} 行</span>
      <span title={data.content_sha256} className="text-[10px] text-slate-400">{data.source_kind === 'workspace' ? `工作区 · ${data.content_sha256.slice(0, 8)}` : `索引版本 ${data.head_commit?.slice(0, 8) || data.index_epoch}`}</span>
      <button className="wb-button ml-auto" onClick={() => workbenchStore.getState().selectFile(path, lineno, null, undefined, 'workspace')}>查看当前文件</button>
    </header>
    {data.workspace_changed && <p role="status" className="text-xs leading-6 text-amber-700">当前显示已索引的源码快照，磁盘文件已有修改。可从项目菜单更新索引。</p>}
    <div className="flex flex-wrap items-center gap-2">
      <button className="wb-button" disabled={data.start_line <= 1} onClick={() => move(data.start_line - 200)}>前 200 行</button>
      <button className="wb-button" disabled={data.end_line >= data.total_lines} onClick={() => move(data.end_line + 1)}>后 200 行</button>
      <form className="flex items-center gap-1" onSubmit={e => { e.preventDefault(); const line = Number(jump); if (Number.isInteger(line) && line > 0) move(line) }}>
        <input type="number" aria-label="跳到行号" min={1} max={data.total_lines} value={jump} onChange={e => setJump(e.target.value)} className="wb-input w-20" /><button className="wb-button">跳行</button>
      </form>
      <button type="button" className="wb-primary" disabled={!selection} onClick={ask}>问选中代码</button>
    </div>
    <CodeViewer code={data.content} startLine={data.start_line} language={path.endsWith('.py') ? 'python' : /\.tsx?$/.test(path) ? 'typescript' : /\.jsx?$/.test(path) ? 'javascript' : path.endsWith('.sql') ? 'sql' : 'text'} viewKey={`${projectId}:${path}:${data.content_sha256}:${data.start_line}`} onSelection={setSelection} />
    <p className="text-[10px] text-slate-400">只读源码窗口 · 查找仅作用于当前已加载的 {data.end_line - data.start_line + 1} 行</p>
  </article>
}
