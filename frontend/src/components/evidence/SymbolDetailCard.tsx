/**
 * 符号详情卡：定义（Monaco 只读）+ 调用者/被调者（不确定的标 ⚠）。
 * 数据来自 `GET /projects/{id}/symbols/{qualname}`（mock 下同样形状）。
 */
import { useEffect, useState } from 'react'
import { AlertTriangle, ArrowRightLeft, Share2 } from 'lucide-react'
import { api } from '../../api/dataSource'
import type { RelationRef, SymbolDetail } from '../../api/types'
import { projectStore } from '../../store/projectStore'
import { viewStore } from '../../store/viewStore'
import CodeViewer from './CodeViewer'

function RelationList({ title, items }: { title: string; items: RelationRef[] }) {
  if (items.length === 0) return null
  return (
    <div className="mt-2.5">
      <h4 className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">{title}</h4>
      <ul className="mt-1 space-y-1">
        {items.slice(0, 12).map((r, i) => (
          <li key={`${r.qualname}:${i}`} className="flex items-start gap-1.5 text-[11px] leading-relaxed">
            {r.uncertain ? (
              <span
                className="mt-px flex shrink-0 items-center gap-0.5 text-warning"
                title={r.note ?? '静态分析不确定'}
              >
                <AlertTriangle size={11} strokeWidth={1.8} /> 可能
              </span>
            ) : (
              <span className="mt-px shrink-0 text-slate-300">·</span>
            )}
            <span className="min-w-0 truncate font-mono text-slate-600" title={`${r.path}:${r.lineno}`}>
              {r.qualname}
            </span>
            <span className="ml-auto shrink-0 font-mono text-[10px] text-slate-400">
              :{r.lineno}
            </span>
          </li>
        ))}
        {items.length > 12 && (
          <li className="text-[10px] text-slate-400">…共 {items.length} 条</li>
        )}
      </ul>
    </div>
  )
}

export default function SymbolDetailCard({ qualname }: { qualname: string }) {
  const projectId = projectStore.getState().currentProjectId
  // 状态带"属于哪个 qualname"的键：换符号时旧数据自然失效（显示加载态），
  // 不用在 effect 里同步清空——同步 setState 会触发级联渲染。
  const [state, setState] = useState<{ for: string; detail: SymbolDetail } | null>(null)
  const [failed, setFailed] = useState<{ for: string; message: string } | null>(null)

  useEffect(() => {
    let alive = true
    if (projectId === null) return
    api
      .getSymbol(projectId, qualname)
      .then((d) => alive && setState({ for: qualname, detail: d }))
      .catch((e) =>
        alive && setFailed({ for: qualname, message: e instanceof Error ? e.message : String(e) }),
      )
    return () => {
      alive = false
    }
  }, [projectId, qualname])

  const error = failed?.for === qualname ? failed.message : ''
  const detail = state?.for === qualname ? state.detail : null

  if (error) {
    return <p className="px-1 py-6 text-center text-xs text-danger">{error}</p>
  }
  if (!detail) {
    return <p className="px-1 py-6 text-center text-xs text-slate-400">读取符号…</p>
  }

  return (
    <article className="space-y-2.5">
      <header>
        <div className="flex items-start gap-2">
          <p className="min-w-0 flex-1 break-all font-mono text-[11px] text-slate-400">
            {detail.qualname}
          </p>
          <button
            type="button"
            onClick={() => viewStore.getState().openGraph(detail.qualname)}
            className="flex shrink-0 items-center gap-1 rounded-lg border border-slate-200 px-1.5 py-0.5 text-[10px] text-slate-500 transition-colors hover:border-accent hover:text-accent"
            title="以这个符号为中心打开关系图"
          >
            <Share2 size={10} strokeWidth={1.8} /> 关系图
          </button>
        </div>
        <h3 className="mt-0.5 flex items-center gap-1.5 text-sm font-semibold text-slate-800">
          <span className="rounded bg-accent-soft px-1.5 py-px font-mono text-[10px] font-medium uppercase text-accent">
            {detail.kind}
          </span>
          {detail.name}
          {detail.is_async && <span className="text-[10px] text-slate-400">async</span>}
        </h3>
        <p className="mt-1 font-mono text-[10.5px] text-slate-400">
          {detail.path}:{detail.lineno}–{detail.end_lineno} · {detail.n_lines} 行 · 入度{' '}
          {detail.in_degree} · 出度 {detail.out_degree}
        </p>
      </header>

      {detail.docstring && (
        <p className="rounded-lg bg-slate-50 px-2.5 py-2 text-[11px] leading-relaxed text-slate-600">
          {detail.docstring}
        </p>
      )}

      <CodeViewer
        code={detail.source}
        language={detail.path.endsWith('.py') ? 'python' : 'text'}
        startLine={detail.lineno}
      />

      {detail.ambiguous && detail.alternatives && detail.alternatives.length > 0 && (
        <p className="rounded-lg bg-warning/10 px-2.5 py-1.5 text-[11px] text-warning">
          该名字有 {detail.alternatives.length + 1} 处定义，当前显示第一处。
        </p>
      )}

      <div className="flex items-center gap-1.5 text-[11px] text-slate-500">
        <ArrowRightLeft size={12} strokeWidth={1.7} className="text-slate-400" />
        调用关系
      </div>
      <RelationList title={`调用者（${detail.callers.length}）`} items={detail.callers} />
      <RelationList title={`被调（${detail.callees.length}）`} items={detail.callees} />
      <RelationList title={`引用处（${detail.references.length}）`} items={detail.references} />
    </article>
  )
}
