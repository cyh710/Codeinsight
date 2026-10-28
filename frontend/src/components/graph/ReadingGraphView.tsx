import { openSource } from '../exploration/actions'
/** 静态调用的阅读视图；展示项、测试折叠和证据位置都由现有索引派生。 */
import { useEffect, useMemo, useState } from 'react'
import { useStore } from 'zustand'
import { ArrowRight, Code2, Focus, Loader2, Search } from 'lucide-react'
import { api } from '../../api/dataSource'
import type { Flow, GraphNode, GraphResponse } from '../../api/types'
import { projectStore } from '../../store/projectStore'
import { workbenchStore } from '../../store/workbenchStore'
import { isTestCode, readingGraph, type ReadingConnection } from './readingGraphModel'

const kindName: Record<string, string> = {
  function: '函数',
  method: '方法',
  class: '类',
  module: '模块',
  property: '属性',
  constant: '常量',
}

export default function ReadingGraphView({
  projectId,
  focus,
  onFocus,
}: {
  projectId: number | null
  focus: string | null
  onFocus: (qualname: string) => void
}) {
  const files = useStore(projectStore, (s) => s.files)
  const [attempt, setAttempt] = useState(0)
  const key = `${projectId}|${focus}|${attempt}`
  const [result, setResult] = useState<{
    key: string
    data?: GraphResponse
    error?: string
  } | null>(null)
  const [concepts, setConcepts] = useState<{
    projectId: number
    names: Map<string, string>
  } | null>(null)
  useEffect(() => {
    if (projectId === null) return
    let alive = true
    api
      .listConcepts(projectId)
      .then((response) => {
        if (alive)
          setConcepts({
            projectId,
            names: new Map(response.items.map((item) => [item.concept_id, item.name])),
          })
      })
      .catch(() => {
        // 概念名称缺失只影响辅助标签；不阻断已有代码关系的阅读。
        if (alive) setConcepts({ projectId, names: new Map() })
      })
    return () => {
      alive = false
    }
  }, [projectId])
  useEffect(() => {
    if (projectId === null || !focus) return
    let alive = true
    api
      .getGraph(projectId, { qualname: focus, depth: 1, kinds: ['call'], max_nodes: 200 })
      .then((data) => {
        if (alive) setResult({ key, data })
      })
      .catch((error) => {
        if (alive) setResult({ key, error: error instanceof Error ? error.message : String(error) })
      })
    return () => {
      alive = false
    }
  }, [projectId, focus, key])
  const data = result?.key === key ? result.data : undefined
  const model = useMemo(() => (data ? readingGraph(data, files) : null), [data, files])
  const names = concepts?.projectId === projectId ? concepts.names : new Map<string, string>()
  if (projectId === null)
    return <p className="p-8 text-center text-sm text-slate-400">先在左栏选择一个项目。</p>
  if (!focus) return <FocusChooser key={projectId} projectId={projectId} onFocus={onFocus} />
  if (result?.key === key && result.error)
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
        <p role="alert" className="text-sm text-danger">
          {result.error}
        </p>
        <button
          className="rounded-lg bg-accent px-3 py-2 text-xs text-white"
          onClick={() => setAttempt((n) => n + 1)}
        >
          重新读取
        </button>
        <p className="text-xs text-slate-400">也可以用上方搜索换一处代码。</p>
      </div>
    )
  if (!data || !model)
    return (
      <p className="flex items-center justify-center gap-2 p-10 text-sm text-slate-400">
        <Loader2 size={15} className="animate-spin" />
        正在读取直接调用关系…
      </p>
    )
  if (!model.center)
    return (
      <p className="p-8 text-sm text-slate-500">当前返回的关系中没有这个代码位置，请重新搜索。</p>
    )
  const center = model.center
  return (
    <div className="reading-graph h-full overflow-y-auto" key={key}>
      <header className="reading-graph-heading">
        <h2 className="mt-2 break-words text-base font-semibold text-slate-800">
          {center.name} 的调用关系
        </h2>
      </header>
      {data.truncated && (
        <p
          role="status"
          className="mx-4 mb-5 rounded-lg border border-warning/20 bg-warning/10 px-3 py-2 text-xs leading-6 text-warning"
        >
          当前仅返回部分关系，下面的数量不代表全部。可以更换中心继续查看，或进入高级全图调整范围。
        </p>
      )}
      <div className="reading-graph-columns">
        <ConnectionColumn
          key={`${key}-in`}
          title="谁调用它"
          direction="incoming"
          connections={model.callers}
          center={center}
          onFocus={onFocus}
          names={names}
        />
        <section className="reading-graph-center" aria-label="当前代码">
          <p className="mb-3 text-xs font-medium text-accent">当前代码</p>
          <div className="rounded-xl border border-accent/35 bg-bg-elevated p-3 shadow-sm ring-4 ring-accent-soft/50">
            <p className="text-[10px] text-accent">{kindName[center.kind] ?? center.kind}</p>
            <h3
              className="mt-2 break-words text-sm font-semibold leading-6 text-slate-800"
              title={center.qualname}
            >
              {center.name}
            </h3>
            <p
              className="mt-2 break-all text-[11px] leading-5 text-slate-400"
              title={`${center.path}:${center.lineno}`}
            >
              {center.path.split('/').slice(-2).join('/')}:{center.lineno}
            </p>
            <button
              className="mt-4 flex items-center gap-1 text-xs text-accent hover:underline"
              onClick={() => openSource(center)}
            >
              <Code2 size={13} />
              查看源码
            </button>
            {model.recursiveCalls.length > 0 && (
              <p className="mt-3 border-t border-slate-100 pt-3 text-[11px] leading-5 text-slate-500">
                索引中还记录了它对自身的调用。
              </p>
            )}
            <ConceptLinks node={center} names={names} />
          </div>
        </section>
        <ConnectionColumn
          key={`${key}-out`}
          title="它调用什么"
          direction="outgoing"
          connections={model.callees}
          center={center}
          onFocus={onFocus}
          names={names}
        />
      </div>
      <footer className="mx-4 mb-6 mt-8 border-t border-slate-200/70 pt-4 text-[11px] leading-6 text-slate-400">
        箭头表示调用关系，不表示运行时的执行先后。这里只展示索引中可定位的直接调用；外部库与未解析的动态调用未列入。
        继承、装饰器等关系可在“高级全图”中查看。
      </footer>
    </div>
  )
}

function ConceptLinks({ node, names }: { node: GraphNode; names: Map<string, string> }) {
  if (!node.concept_ids.length) return null
  return (
    <details className="mt-3 border-t border-slate-100 pt-2 text-[11px] text-slate-400">
      <summary className="cursor-pointer">相关概念 · {node.concept_ids.length}</summary>
      <div className="mt-2 flex flex-wrap gap-2">
        {node.concept_ids.map((id) => (
          <button
            key={id}
            onClick={() => workbenchStore.getState().openConcept(id)}
            className="text-left text-accent hover:underline"
          >
            {names.get(id) ?? id}
          </button>
        ))}
      </div>
    </details>
  )
}

function ConnectionColumn({
  title,
  connections,
  center,
  direction,
  onFocus,
  names,
}: {
  title: string
  connections: ReadingConnection[]
  center: GraphNode
  direction: 'incoming' | 'outgoing'
  onFocus: (qualname: string) => void
  names: Map<string, string>
}) {
  const normal = connections.filter((connection) => !connection.isTest)
  const tests = connections.filter((connection) => connection.isTest)
  const [expanded, setExpanded] = useState(false)
  return (
    <section className="min-w-0" aria-label={title}>
      <h3 className="mb-3 flex items-baseline gap-2 text-xs font-semibold text-slate-600">
        {title}
        <span className="font-mono text-[11px] font-normal text-slate-400">{normal.length}</span>
      </h3>
      <div className="space-y-3">
        {normal.slice(0, expanded ? undefined : 4).map((connection) => (
          <ConnectionCard
            key={connection.node.id}
            connection={connection}
            center={center}
            direction={direction}
            onFocus={onFocus}
            names={names}
          />
        ))}
        {normal.length > 4 && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="w-full rounded-lg border border-dashed border-slate-300 px-2 py-2 text-xs leading-5 text-accent hover:bg-accent-soft/40"
          >
            {expanded ? '收起更多关系' : `展开其余 ${normal.length - 4} 项`}
          </button>
        )}
        {!normal.length && (
          <p className="rounded-lg border border-dashed border-slate-200 p-3 text-xs leading-6 text-slate-400">
            当前返回的关系中没有{direction === 'incoming' ? '非测试调用者' : '非测试调用目标'}。
          </p>
        )}
      </div>
      {tests.length > 0 && (
        <details className="mt-4 rounded-lg border border-slate-200/80 p-2.5">
          <summary className="cursor-pointer text-xs leading-5 text-slate-500">
            {direction === 'incoming' ? '测试中的调用' : '调用到的测试'} · {tests.length}
          </summary>
          <div className="mt-3 space-y-3">
            {tests.map((connection) => (
              <ConnectionCard
                key={connection.node.id}
                connection={connection}
                center={center}
                direction={direction}
                onFocus={onFocus}
                names={names}
              />
            ))}
          </div>
        </details>
      )}
    </section>
  )
}

function ConnectionCard({
  connection,
  center,
  direction,
  onFocus,
  names,
}: {
  connection: ReadingConnection
  center: GraphNode
  direction: 'incoming' | 'outgoing'
  onFocus: (qualname: string) => void
  names: Map<string, string>
}) {
  const { node, edges } = connection
  const uncertain = edges.some((edge) => edge.uncertain)
  const callPath = direction === 'incoming' ? node.path : center.path
  return (
    <article className="reading-connection rounded-xl border border-slate-200 bg-bg-elevated p-3 shadow-sm">
      <p className="flex flex-wrap items-center gap-1.5 text-[10px] text-slate-400">
        {kindName[node.kind] ?? node.kind}
        {uncertain && (
          <span className="rounded bg-warning/10 px-1 text-warning">
            {edges.every((edge) => edge.uncertain) ? '可能的调用' : '含待核对调用'}
          </span>
        )}
      </p>
      <button
        onClick={() =>
          openSource(node)
        }
        className="mt-1.5 block w-full break-words text-left text-[13px] font-semibold leading-6 text-slate-700 hover:text-accent"
        title={node.qualname}
      >
        {node.name}
      </button>
      <p
        className="mt-1 break-all font-mono text-[10px] leading-5 text-slate-400"
        title={node.path}
      >
        {node.path.split('/').slice(-2).join('/')}:{node.lineno}
      </p>
      <div className="mt-3 flex flex-wrap gap-x-3 gap-y-2 border-t border-slate-100 pt-2.5 text-[11px]">
        <button
          onClick={() => onFocus(node.qualname)}
          className="flex items-center gap-1 text-accent hover:underline"
        >
          <Focus size={11} />
          以此为中心
        </button>
        <button
          onClick={() => openSource(node)}
          className="text-slate-500 hover:text-accent"
        >
          源码
        </button>
      </div>
      <details className="mt-2 text-[10px] leading-5 text-slate-400">
        <summary className="cursor-pointer">调用依据 · {edges.length} 处</summary>
        {edges.map((edge, index) =>
          edge.lineno !== null ? (
            <button
              key={index}
              className="mt-1 block text-left text-accent hover:underline"
              onClick={() => openSource({ path: callPath, lineno: edge.lineno!, target: (direction === 'incoming' ? node.target : center.target) ? { ...(direction === 'incoming' ? node.target! : center.target!), lineno: edge.lineno!, end_lineno: edge.lineno! } : undefined })}
            >
              {callPath}:{edge.lineno}
              {edge.uncertain ? ` · 待核对 ${Math.round(edge.confidence * 100)}%` : ''}
            </button>
          ) : (
            <p key={index}>当前关系未记录调用行号。</p>
          ),
        )}
        <ConceptLinks node={node} names={names} />
      </details>
    </article>
  )
}

function FocusChooser({
  projectId,
  onFocus,
}: {
  projectId: number
  onFocus: (qualname: string) => void
}) {
  const files = useStore(projectStore, (s) => s.files)
  const [result, setResult] = useState<{ flows: Flow[]; nodes: GraphNode[]; error: string } | null>(
    null,
  )
  useEffect(() => {
    let alive = true
    Promise.allSettled([
      api.listFlows(projectId),
      api.getGraph(projectId, { kinds: ['call'], max_nodes: 12, depth: 1 }),
    ]).then(([flows, graph]) => {
      if (!alive) return
      setResult({
        flows: flows.status === 'fulfilled' ? flows.value.items : [],
        nodes: graph.status === 'fulfilled' ? graph.value.nodes : [],
        error:
          flows.status === 'rejected' || graph.status === 'rejected'
            ? '部分入口暂时未能读取，可以用上方搜索查找具体函数。'
            : '',
      })
    })
    return () => {
      alive = false
    }
  }, [projectId])
  const flows = result?.flows.filter((flow) => flow.entry_qualname) ?? []
  const candidates = result?.nodes.filter((node) => !isTestCode(node.path, files)).slice(0, 6) ?? []
  return (
    <div className="h-full overflow-y-auto px-6 py-8">
      <div className="max-w-2xl">
        <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-xl border border-accent/15 bg-accent-soft/50 text-accent">
          <Search size={19} />
        </div>
        <h2 className="text-lg font-semibold leading-8 text-slate-800">先选一处你想读懂的代码</h2>
        <div className="my-6 flex flex-wrap items-center gap-2 text-xs text-slate-400">
          <span>谁调用它</span>
          <ArrowRight size={14} />
          <span className="rounded-md bg-accent-soft px-2 py-1 text-accent">当前代码</span>
          <ArrowRight size={14} />
          <span>它调用什么</span>
        </div>
        {!result && <p className="text-xs text-slate-400">正在读取可探索的代码…</p>}
        {result?.error && (
          <p role="status" className="mb-4 text-xs leading-6 text-warning">
            {result.error}
          </p>
        )}
        {flows.length > 0 && (
          <section className="mb-7" aria-label="已索引的流程入口">
            <h3 className="mb-3 text-xs font-medium text-slate-500">已索引的流程入口</h3>
            <div className="grid gap-2">
              {flows.slice(0, 6).map((flow) => (
                <button
                  key={flow.id}
                  className="flex items-center gap-3 rounded-xl border border-slate-200 bg-bg-elevated p-3 text-left hover:border-accent/30 hover:bg-accent-soft/20"
                  onClick={() => onFocus(flow.entry_qualname!)}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block break-words text-[13px] font-medium text-slate-700">
                      {flow.name}
                    </span>
                    <span className="mt-1 block break-all font-mono text-[10px] leading-5 text-slate-400">
                      {flow.entry_qualname}
                    </span>
                  </span>
                  <ArrowRight size={14} className="shrink-0 text-slate-400" />
                </button>
              ))}
            </div>
          </section>
        )}
        {candidates.length > 0 && (
          <section aria-label="可探索的代码">
            <h3 className="mb-3 text-xs font-medium text-slate-500">
              可探索的代码
            </h3>
            <div className="grid gap-2 sm:grid-cols-2">
              {candidates.map((node) => (
                <button
                  key={node.id}
                  onClick={() => onFocus(node.qualname)}
                  className="min-w-0 rounded-xl border border-slate-200 bg-bg-elevated p-3 text-left hover:border-accent/30 hover:bg-accent-soft/20"
                >
                  <span className="block break-words text-[13px] font-medium text-slate-700">
                    {node.name}
                  </span>
                  <span className="mt-1 block break-all font-mono text-[10px] leading-5 text-slate-400">
                    {node.path}
                  </span>
                </button>
              ))}
            </div>
          </section>
        )}
        {result && !flows.length && !candidates.length && !result.error && (
          <p className="text-sm leading-7 text-slate-400">
            还没有可推荐的入口。可以在上方搜索，或从左侧打开函数，再点击右栏的“关系图”。
          </p>
        )}
      </div>
    </div>
  )
}
