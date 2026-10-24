/**
 * 演进时间线（源文档 §2.4）：每次索引/外部变更一格。
 *
 * 数据来自 `GET /projects/{id}/timeline`（契约 §7.2）。展开一格的明细时才
 * 去拉 `/changes?since=<commit>`——列表不做 N 次请求。
 *
 * 全量索引没有 diff，明细区如实说「没有可比的上一版」，不编造增删。
 */
import { useEffect, useState, type ReactNode } from 'react'
import { useStore } from 'zustand'
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  FileMinus,
  FilePlus,
  FilePen,
  Loader2,
  RefreshCw,
} from 'lucide-react'
import { api } from '../../api/dataSource'
import type { ChangesResponse, TimelineItem, TimelineResponse } from '../../api/types'
import { projectStore } from '../../store/projectStore'
import { workbenchStore } from '../../store/workbenchStore'
import { fileCountsLabel, formatTimelineTime, modeLabel, shortCommit } from './timelineModel'

export default function TimelineView() {
  const projectId = useStore(projectStore, (s) => s.currentProjectId)
  const [reload, setReload] = useState(0)
  const [expanded, setExpanded] = useState<string | null>(null)
  const requestKey = `${projectId ?? 'none'}|${reload}`
  // 结果带请求 key：key 不匹配就是载入中，effect 里不写同步 state。
  const [result, setResult] = useState<{
    key: string
    data?: TimelineResponse
    error?: string
  } | null>(null)

  useEffect(() => {
    if (projectId === null) return
    let alive = true
    api
      .getTimeline(projectId, 30)
      .then((res) => alive && setResult({ key: requestKey, data: res }))
      .catch(
        (e) =>
          alive &&
          setResult({ key: requestKey, error: e instanceof Error ? e.message : String(e) }),
      )
    return () => {
      alive = false
    }
  }, [projectId, reload, requestKey])

  const data = result?.key === requestKey ? (result.data ?? null) : null
  const error = result?.key === requestKey ? (result.error ?? '') : ''
  const loading = projectId !== null && result?.key !== requestKey

  if (projectId === null) {
    return <p className="py-10 text-center text-xs text-slate-400">先选择一个项目。</p>
  }

  if (error) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
        <p className="text-xs text-danger">{error}</p>
        <button
          type="button"
          onClick={() => setReload((n) => n + 1)}
          className="rounded-lg bg-accent px-2.5 py-1 text-[11px] text-white hover:bg-accent-hover"
        >
          重试
        </button>
      </div>
    )
  }

  if (!data || (loading && !data)) {
    return (
      <div className="flex h-full items-center justify-center gap-1.5 text-[11px] text-slate-500">
        <Loader2 size={12} className="animate-spin" /> 读取时间线…
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto px-4 py-4">
      <div className="mx-auto max-w-3xl">
        <div className="mb-3 flex items-center gap-2">
          <h2 className="text-sm font-semibold text-slate-700">演进时间线</h2>
          <span className="text-[10.5px] text-slate-400">
            {data.total} 次索引/变更 · 当前 {shortCommit(data.head)}
          </span>
          <button
            type="button"
            onClick={() => setReload((n) => n + 1)}
            className="ml-auto flex items-center gap-1 rounded-lg px-2 py-1 text-[10.5px] text-slate-500 transition-colors hover:bg-accent-soft hover:text-accent"
            title="重新读取"
          >
            <RefreshCw size={11} strokeWidth={1.8} className={loading ? 'animate-spin' : ''} />
            刷新
          </button>
        </div>

        {data.items.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-200 px-4 py-10 text-center">
            <p className="text-xs text-slate-500">还没有索引记录。</p>
            <p className="mt-1 text-[11px] text-slate-400">
              跑一次 <code className="font-mono">ci index</code> 之后，这里会出现第一次快照。
            </p>
          </div>
        ) : (
          <ol className="relative ml-1.5 border-l border-slate-200 pl-4">
            {data.items.map((item) => (
              <TimelineEntry
                key={item.id}
                projectId={projectId}
                item={item}
                open={expanded === item.id}
                onToggle={() => setExpanded((cur) => (cur === item.id ? null : item.id))}
              />
            ))}
          </ol>
        )}
      </div>
    </div>
  )
}

function TimelineEntry({
  projectId,
  item,
  open,
  onToggle,
}: {
  projectId: number
  item: TimelineItem
  open: boolean
  onToggle: () => void
}) {
  const counts = fileCountsLabel(item)
  const stale = item.stale_design_decisions.length
  return (
    <li className="relative pb-3">
      <span
        className={`absolute -left-[21px] top-2.5 h-2 w-2 rounded-full ring-2 ring-bg ${
          item.kind === 'change'
            ? 'bg-warning'
            : item.mode === 'incremental'
              ? 'bg-accent'
              : 'bg-slate-400'
        }`}
      />
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="w-full rounded-xl border border-slate-200 bg-bg-elevated px-3 py-2.5 text-left shadow-1 transition-colors hover:border-slate-300"
      >
        <div className="flex flex-wrap items-center gap-1.5">
          <span
            className={`rounded px-1.5 py-px text-[9.5px] ${
              item.mode === 'incremental' || item.kind === 'change'
                ? 'bg-accent-soft text-accent'
                : 'bg-slate-100 text-slate-500'
            }`}
          >
            {modeLabel(item)}
          </span>
          <span className="text-[10.5px] text-slate-400">{formatTimelineTime(item.at)}</span>
          <span className="font-mono text-[10px] text-slate-400">{shortCommit(item.head_commit)}</span>
          {item.kind === 'index' && item.base_commit && (
            <span className="font-mono text-[9.5px] text-slate-300">
              ← {shortCommit(item.base_commit)}
            </span>
          )}
          {!item.ok && (
            <span className="flex items-center gap-0.5 rounded bg-danger-soft px-1.5 py-px text-[9.5px] text-danger">
              <AlertTriangle size={9} /> 失败
            </span>
          )}
          <span className="ml-auto text-slate-300">
            {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          </span>
        </div>
        <p className="mt-1 line-clamp-2 text-[11.5px] leading-relaxed text-slate-600">
          {item.summary}
        </p>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-slate-500">
          {counts ? (
            <span className="font-mono">{counts}</span>
          ) : (
            <span>
              {item.files_total ?? item.files.total} 个文件
              {item.symbols_added !== null ? ` · ${item.symbols_added} 个符号` : ''}
            </span>
          )}
          {item.symbols_changed !== null && <span>{item.symbols_changed} 个符号变化</span>}
          {stale > 0 && (
            <span className="flex items-center gap-0.5 text-warning">
              <AlertTriangle size={9} /> {stale} 条设计说明过期
            </span>
          )}
        </div>
      </button>
      {open && (
        <EntryDetail projectId={projectId} item={item} />
      )}
    </li>
  )
}

function EntryDetail({ projectId, item }: { projectId: number; item: TimelineItem }) {
  // 全量索引没有 diff：直接说明，不用一个空壳去请求。
  const comparable =
    item.kind === 'change' || (item.kind === 'index' && item.mode === 'incremental')
  const [detail, setDetail] = useState<ChangesResponse | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!comparable || !item.head_commit) return
    let alive = true
    api
      .getChanges(projectId, item.head_commit)
      .then((res) => alive && setDetail(res))
      .catch(() => alive && setFailed(true))
    return () => {
      alive = false
    }
  }, [comparable, item.head_commit, projectId])

  return (
    <div className="mt-1.5 space-y-2 rounded-xl bg-slate-50/70 px-3 py-2.5">
      {item.stale_design_decisions.length > 0 && (
        <div className="rounded-lg bg-warning/10 px-2 py-1.5 text-[11px] text-warning">
          <p className="font-medium">这些设计说明在当前代码里找不到证据了：</p>
          <ul className="mt-1 space-y-0.5">
            {item.stale_design_decisions.map((d) => (
              <li key={d.doc_id} className="truncate" title={`${d.doc_id} ${d.title}`}>
                · {d.doc_id} {d.title}
              </li>
            ))}
          </ul>
        </div>
      )}

      {!comparable ? (
        <p className="text-[10.5px] leading-relaxed text-slate-400">
          全量重建没有可比的上一版，因此没有文件级 diff。增量索引才会有增删改明细。
        </p>
      ) : failed ? (
        <p className="text-[10.5px] text-danger">变更明细读取失败。</p>
      ) : !detail ? (
        <p className="flex items-center gap-1 text-[10.5px] text-slate-400">
          <Loader2 size={10} className="animate-spin" /> 读取变更明细…
        </p>
      ) : (
        <ChangeDetail detail={detail} />
      )}
    </div>
  )
}

function ChangeDetail({ detail }: { detail: ChangesResponse }) {
  const hasFiles =
    detail.files.added.length + detail.files.modified.length + detail.files.deleted.length > 0
  return (
    <div className="space-y-2">
      {detail.summary && (
        <p className="text-[11px] leading-relaxed text-slate-600">{detail.summary}</p>
      )}
      {hasFiles && (
        <div className="grid gap-2 sm:grid-cols-3">
          <FileGroup icon={<FilePlus size={10} />} title="新增" tone="text-success" files={detail.files.added} />
          <FileGroup icon={<FilePen size={10} />} title="修改" tone="text-accent" files={detail.files.modified} />
          <FileGroup icon={<FileMinus size={10} />} title="删除" tone="text-danger" files={detail.files.deleted} deleted />
        </div>
      )}
      {detail.changed_symbols.length > 0 && (
        <div>
          <h4 className="text-[9.5px] font-semibold uppercase tracking-wider text-slate-400">
            符号变化（{detail.changed_symbols.length}）
          </h4>
          <ul className="mt-0.5 space-y-0.5">
            {detail.changed_symbols.slice(0, 10).map((symbol, i) => (
              <li key={`${symbol.qualname}:${i}`} className="flex items-center gap-1.5 text-[10.5px]">
                <span className="shrink-0 rounded bg-slate-100 px-1 py-px text-[9px] text-slate-500">
                  {symbol.change}
                </span>
                <button
                  type="button"
                  disabled={symbol.change === 'removed'}
                  onClick={() =>
                    workbenchStore.getState().selectSymbol(symbol.qualname, symbol.path)
                  }
                  className="min-w-0 flex-1 truncate text-left font-mono text-slate-600 enabled:hover:text-accent disabled:text-slate-400"
                  title={`${symbol.path}:${symbol.lineno}`}
                >
                  {symbol.qualname}
                </button>
                <span className="shrink-0 font-mono text-[9px] text-slate-400">
                  :{symbol.lineno}
                </span>
              </li>
            ))}
            {detail.changed_symbols.length > 10 && (
              <li className="text-[9.5px] text-slate-400">
                …共 {detail.changed_symbols.length} 个
              </li>
            )}
          </ul>
        </div>
      )}
      {detail.impacted.modules.length > 0 && (
        <p className="text-[10.5px] text-slate-500">
          影响模块：
          <span className="font-mono text-slate-600">{detail.impacted.modules.slice(0, 6).join('、')}</span>
          {detail.impacted.modules.length > 6 ? ` 等 ${detail.impacted.modules.length} 个` : ''}
        </p>
      )}
      {(detail.tests.length > 0 || detail.stale_design_decisions.length > 0) && (
        <p className="text-[10px] text-slate-400">
          {detail.tests.length > 0 && `关联测试 ${detail.tests.length} 条`}
          {detail.tests.length > 0 && detail.stale_design_decisions.length > 0 && ' · '}
          {detail.stale_design_decisions.length > 0 &&
            `过期设计说明 ${detail.stale_design_decisions.length} 条`}
        </p>
      )}
      {!hasFiles && detail.changed_symbols.length === 0 && (
        <p className="text-[10.5px] text-slate-400">这次变更没有记录到文件或符号级差异。</p>
      )}
    </div>
  )
}

function FileGroup({
  icon,
  title,
  tone,
  files,
  deleted = false,
}: {
  icon: ReactNode
  title: string
  tone: string
  files: Array<{ path: string; changed_symbols?: number }>
  deleted?: boolean
}) {
  if (files.length === 0) return <div />
  return (
    <div>
      <h4 className={`flex items-center gap-1 text-[9.5px] font-semibold uppercase tracking-wider ${tone}`}>
        {icon} {title}（{files.length}）
      </h4>
      <ul className="mt-0.5 space-y-0.5">
        {files.slice(0, 6).map((file) => (
          <li key={file.path}>
            <button
              type="button"
              disabled={deleted}
              onClick={() => workbenchStore.getState().selectFile(file.path, 1)}
              className="w-full truncate text-left font-mono text-[9.5px] text-slate-500 enabled:hover:text-accent disabled:text-slate-400 disabled:line-through"
              title={file.path}
            >
              {file.path}
              {file.changed_symbols ? ` (${file.changed_symbols})` : ''}
            </button>
          </li>
        ))}
        {files.length > 6 && (
          <li className="text-[9px] text-slate-400">…共 {files.length} 个</li>
        )}
      </ul>
    </div>
  )
}
