import { openSource } from '../exploration/actions'
/**
 * 关系图（源文档 §2.2-6/7）：中心符号的 N 跳邻域。
 *
 * 交互约定：
 * - **单击节点** → 右栏符号详情（调用者/被调者/源码）；
 * - **双击节点** → 直接打开该符号所在文件的那一行；
 * - **点节点上的概念标签** → 右栏概念卡（代码 → 知识，§2.6 双向）；
 * - 图的截断必须显示：只画了一部分却不说，比画错更糟。
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useStore } from 'zustand'
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  type NodeTypes,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { Loader2, RotateCcw, Search } from 'lucide-react'
import { api } from '../../api/dataSource'
import {
  GRAPH_EDGE_KINDS,
  type EdgeKind,
  type GraphNode,
  type GraphResponse,
  type SymbolListItem,
} from '../../api/types'
import { projectStore } from '../../store/projectStore'
import { viewStore } from '../../store/viewStore'
import { workbenchStore } from '../../store/workbenchStore'
import { NODE_WIDTH, layoutGraph } from './graphLayout'

const EDGE_COLOR: Record<string, string> = {
  call: '#64748b',
  inherits: '#7c3aed',
  decorator: '#d97706',
  references: '#0d9488',
  imports: '#94a3b8',
  returns: '#94a3b8',
}

const EDGE_LABEL: Record<string, string> = {
  call: '调用',
  inherits: '继承',
  decorator: '装饰器',
  references: '引用',
}

const KIND_LABEL: Record<string, string> = {
  module: 'mod',
  class: 'class',
  function: 'fn',
  method: 'method',
  property: 'prop',
  constant: 'const',
}

interface SymbolNodeData {
  node: GraphNode
  isCenter: boolean
}

function SymbolNode({ data }: NodeProps<SymbolNodeData>) {
  const { node, isCenter } = data
  const openConcept = workbenchStore.getState().openConcept
  return (
    <div
      className={`rounded-xl border bg-bg-elevated px-2.5 py-2 text-left shadow-1 transition-colors ${
        isCenter ? 'border-accent ring-2 ring-accent/25' : 'border-slate-200 hover:border-slate-300'
      }`}
      style={{ width: NODE_WIDTH }}
      title={`${node.qualname}\n${node.path}:${node.lineno}–${node.end_lineno}`}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2 !w-2 !border-slate-300 !bg-slate-100"
      />
      <div className="flex items-center gap-1.5">
        <span className="shrink-0 rounded bg-slate-100 px-1 py-px font-mono text-[9px] uppercase tracking-wide text-slate-500">
          {KIND_LABEL[node.kind] ?? node.kind}
        </span>
        {node.is_async && (
          <span className="shrink-0 font-mono text-[9px] text-slate-400">async</span>
        )}
        <span className="min-w-0 flex-1 truncate text-[12px] font-semibold text-slate-800">
          {node.name}
        </span>
        {isCenter && (
          <span className="shrink-0 rounded bg-accent-soft px-1 py-px text-[9px] text-accent">
            中心
          </span>
        )}
      </div>
      <p className="mt-1 truncate font-mono text-[9.5px] text-slate-400">
        {shortPath(node.path)}:{node.lineno}
      </p>
      <div className="mt-1.5 flex min-h-[16px] flex-wrap items-center gap-1">
        {node.concept_ids.slice(0, 2).map((conceptId) => (
          <button
            key={conceptId}
            type="button"
            onClick={(event) => {
              event.stopPropagation()
              openConcept(conceptId)
            }}
            className="nodrag rounded bg-accent-soft/70 px-1.5 py-px text-[9px] text-accent transition-colors hover:bg-accent-soft"
            title={`概念：${conceptId}（点击打开概念卡）`}
          >
            {conceptId}
          </button>
        ))}
        {node.concept_ids.length > 2 && (
          <span className="text-[9px] text-slate-400">+{node.concept_ids.length - 2}</span>
        )}
        <span
          className="ml-auto shrink-0 font-mono text-[9px] text-slate-300"
          title="调用入度 / 出度"
        >
          ←{node.in_degree} →{node.out_degree}
        </span>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="!h-2 !w-2 !border-slate-300 !bg-slate-100"
      />
    </div>
  )
}

const nodeTypes: NodeTypes = { symbol: SymbolNode }

function shortPath(path: string): string {
  const parts = path.split('/')
  return parts.length <= 2 ? path : `…/${parts.slice(-2).join('/')}`
}

// ─── 主体 ────────────────────────────────────────────────────

export default function AdvancedGraphView() {
  return (
    <ReactFlowProvider>
      <GraphCanvas />
    </ReactFlowProvider>
  )
}

function GraphCanvas() {
  const projectId = useStore(projectStore, (s) => s.currentProjectId)
  const graphFocus = useStore(viewStore, (s) => s.graphFocus)
  const graphRequest = useStore(viewStore, (s) => s.graphRequest)

  const [depth, setDepth] = useState(1)
  const [kinds, setKinds] = useState<EdgeKind[]>([...GRAPH_EDGE_KINDS])
  const [reload, setReload] = useState(0)

  // 打开关系图时定位一次；之后点节点不会把整张图重新洗牌。
  // 不用 effect 同步：那会多一帧空图，也会在点节点时把图重排。
  const resolvedFocus = useMemo(() => {
    const panel = workbenchStore.getState().rightPanel
    return graphFocus ?? (panel.mode === 'symbol' ? panel.qualname : null)
    // 只在「重新打开关系图」时重新取（graphRequest 自增）。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphRequest, graphFocus])
  const [focusOverride, setFocusOverride] = useState<{
    request: number
    qualname: string | null
  } | null>(null)
  const focus = focusOverride?.request === graphRequest ? focusOverride.qualname : resolvedFocus
  const setFocus = (qualname: string | null) =>
    setFocusOverride({ request: graphRequest, qualname })

  const kindsKey = kinds.join(',')
  const requestKey = `${projectId ?? 'none'}|${focus ?? ''}|${depth}|${kindsKey}|${reload}`
  // 请求结果带着自己的 key：key 不匹配 = 正在载入，不需要在 effect 里
  // 同步 setLoading(true)（React 19 的 lint 明确禁止，且确实会多一次渲染）。
  const [result, setResult] = useState<{
    key: string
    data?: GraphResponse
    error?: string
  } | null>(null)
  useEffect(() => {
    if (projectId === null) return
    let alive = true
    api
      .getGraph(projectId, {
        ...(focus ? { qualname: focus } : {}),
        depth,
        kinds,
        max_nodes: 80,
      })
      .then((res) => alive && setResult({ key: requestKey, data: res }))
      .catch(
        (e) =>
          alive &&
          setResult({ key: requestKey, error: e instanceof Error ? e.message : String(e) }),
      )
    return () => {
      alive = false
    }
    // kinds 用字符串做依赖：数组每次渲染都是新引用。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, focus, depth, kindsKey, reload, requestKey])
  const data = result?.key === requestKey ? (result.data ?? null) : null
  const error = result?.key === requestKey ? (result.error ?? '') : ''
  const loading = projectId !== null && result?.key !== requestKey

  const graphNodes = useMemo<Node<SymbolNodeData>[]>(() => {
    if (!data) return []
    const positions = layoutGraph(data.nodes, data.edges)
    return data.nodes.map((node) => ({
      id: String(node.id),
      type: 'symbol',
      position: positions.get(node.id) ?? { x: 0, y: 0 },
      data: { node, isCenter: data.center?.qualname === node.qualname },
      style: { width: NODE_WIDTH },
    }))
  }, [data])

  const graphEdges = useMemo<Edge[]>(() => {
    if (!data) return []
    return data.edges.map((edge) => {
      const color = EDGE_COLOR[edge.kind] ?? '#94a3b8'
      return {
        id: `${edge.src}-${edge.dst}-${edge.kind}`,
        source: String(edge.src),
        target: String(edge.dst),
        type: 'smoothstep',
        style: {
          stroke: color,
          strokeWidth: edge.uncertain ? 1.1 : 1.5,
          strokeDasharray: edge.uncertain ? '5 4' : undefined,
        },
        markerEnd: { type: MarkerType.ArrowClosed, color, width: 14, height: 14 },
      }
    })
  }, [data])

  const toggleKind = (kind: EdgeKind) => {
    setKinds((current) =>
      current.includes(kind)
        ? current.length === 1
          ? current
          : current.filter((k) => k !== kind)
        : [...current, kind],
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-slate-200/70 px-3 py-2">
        {projectId !== null && (
          <SymbolSearch
            projectId={projectId}
            onPick={(qualname) => {
              viewStore.getState().setGraphFocus(qualname)
              setFocus(qualname)
            }}
          />
        )}
        <div
          className="flex items-center gap-0.5 rounded-lg bg-slate-100 p-0.5"
          role="group"
          aria-label="跳数"
        >
          {[1, 2, 3].map((n) => (
            <button
              key={n}
              type="button"
              onClick={() => setDepth(n)}
              className={`rounded-md px-2 py-1 text-[10.5px] transition-colors ${
                depth === n
                  ? 'bg-bg-elevated text-slate-700 shadow-1'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
              title={`显示 ${n} 跳以内的关系`}
            >
              {n} 跳
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1" role="group" aria-label="边类型">
          {GRAPH_EDGE_KINDS.map((kind) => {
            const on = kinds.includes(kind)
            return (
              <button
                key={kind}
                type="button"
                onClick={() => toggleKind(kind)}
                aria-pressed={on}
                className={`flex items-center gap-1 rounded-md px-1.5 py-1 text-[10.5px] transition-colors ${
                  on
                    ? 'bg-bg-elevated text-slate-600 shadow-1'
                    : 'text-slate-400 hover:text-slate-600'
                }`}
              >
                <span
                  className="h-1.5 w-1.5 rounded-full"
                  style={{ background: on ? EDGE_COLOR[kind] : '#cbd5e1' }}
                />
                {EDGE_LABEL[kind] ?? kind}
              </button>
            )
          })}
        </div>
        <button
          type="button"
          onClick={() => {
            viewStore.getState().setGraphFocus(null)
            setFocus(null)
          }}
          className="ml-auto flex items-center gap-1 rounded-lg px-2 py-1 text-[10.5px] text-slate-500 transition-colors hover:bg-accent-soft hover:text-accent"
          title="不聚焦任何符号，显示高连接度符号的概览"
        >
          <RotateCcw size={12} strokeWidth={1.8} /> 概览
        </button>
      </div>

      <div className="min-h-0 flex-1">
        {error ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
            <p className="text-xs text-danger">{error}</p>
            <button
              type="button"
              onClick={() => setReload((n) => n + 1)}
              className="rounded-lg bg-accent px-2.5 py-1 text-[11px] text-white hover:bg-accent-hover"
            >
              重试
            </button>
            <p className="text-[11px] text-slate-400">换一个符号，或点右上角「概览」。</p>
          </div>
        ) : data && data.nodes.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
            <p className="text-xs text-slate-500">
              {focus ? '这个符号没有可画的关系。' : '索引里还没有可画的符号关系。'}
            </p>
            <p className="max-w-sm text-[11px] leading-relaxed text-slate-400">
              动态调用（getattr / 反射）静态分析定不了，本来就不会出现；
              指向仓库外的调用也不画——图上不留画不出位置的边。
            </p>
          </div>
        ) : (
          <FlowCanvas
            nodes={graphNodes}
            edges={graphEdges}
            data={data}
            loading={loading}
            onFocus={(qualname) => {
              viewStore.getState().setGraphFocus(qualname)
              setFocus(qualname)
            }}
          />
        )}
      </div>
    </div>
  )
}

function FlowCanvas({
  nodes,
  edges,
  data,
  loading,
  onFocus,
}: {
  nodes: Node<SymbolNodeData>[]
  edges: Edge[]
  data: GraphResponse | null
  loading: boolean
  onFocus: (qualname: string) => void
}) {
  const { fitView } = useReactFlow()
  const rendered = useRef(false)

  useEffect(() => {
    if (!data) return
    // 等 React Flow 量完节点尺寸再适配视口。
    const id = window.setTimeout(() => {
      // minZoom：邻居多时不把整张图缩成米粒。缩到 0.45 还放不下就裁边，
      // 用户可以平移/看缩略图——总比字看不清强。
      void fitView({
        padding: 0.16,
        duration: rendered.current ? 200 : 0,
        minZoom: 0.45,
        maxZoom: 0.9,
      })
      rendered.current = true
    }, 30)
    return () => window.clearTimeout(id)
  }, [data, fitView])

  const openSymbol = (node: SymbolNodeData['node']) => {
    openSource(node)
  }

  return (
    <div className="relative h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.16, minZoom: 0.45, maxZoom: 0.9 }}
        minZoom={0.15}
        maxZoom={1.6}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_event, rfNode) => openSymbol(rfNode.data.node)}
        onNodeDoubleClick={(_event, rfNode) => {
          const node = rfNode.data.node
          openSource(node)
        }}
        onNodeContextMenu={(event, rfNode) => {
          event.preventDefault()
          onFocus(rfNode.data.node.qualname)
        }}
      >
        <Background gap={18} size={1} color="#e2e8f0" />
        <Controls showInteractive={false} />
        <MiniMap
          pannable
          zoomable
          nodeColor={(node: Node<SymbolNodeData>) => (node.data?.isCenter ? '#0369a1' : '#cbd5e1')}
          maskColor="rgba(248, 250, 252, 0.7)"
        />
      </ReactFlow>

      <div className="pointer-events-none absolute left-2.5 top-2.5 flex flex-col gap-1">
        <p className="rounded-md bg-bg-elevated/90 px-2 py-1 text-[10.5px] text-slate-500 shadow-1">
          {data?.center
            ? `以 ${lastSegment(data.center.qualname)} 为中心 · ${data.nodes.length} 节点 / ${data.edges.length} 关系`
            : `高连接度符号概览 · ${data?.nodes.length ?? 0} 节点 / ${data?.edges.length ?? 0} 关系`}
        </p>
        {data?.truncated && (
          <p className="rounded-md bg-warning/10 px-2 py-1 text-[10.5px] text-warning shadow-1">
            节点已达上限，图上不是全部——缩小跳数或换中心再看
          </p>
        )}
        <p className="rounded-md bg-bg-elevated/90 px-2 py-1 text-[10px] text-slate-400 shadow-1">
          单击看详情 · 双击跳到源码 · 右键以它为中心 · 虚线 = 不确定
        </p>
      </div>

      {loading && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-bg/40">
          <span className="flex items-center gap-1.5 rounded-lg bg-bg-elevated px-2.5 py-1.5 text-[11px] text-slate-500 shadow-2">
            <Loader2 size={12} className="animate-spin" /> 载入关系图…
          </span>
        </div>
      )}
    </div>
  )
}

function lastSegment(qualname: string): string {
  const parts = qualname.split('.')
  return parts[parts.length - 1] ?? qualname
}

// ─── 符号搜索 ─────────────────────────────────────────────────

export function SymbolSearch({
  projectId,
  onPick,
}: {
  projectId: number
  onPick: (qualname: string) => void
}) {
  const [query, setQuery] = useState('')
  // 结果带着它对应的查询词：查询变了而新结果还没到，旧结果自然不显示，
  // 不需要在 effect 里同步清空。
  const [results, setResults] = useState<{ query: string; items: SymbolListItem[]; error?: string }>({
    query: '',
    items: [],
  })
  const [open, setOpen] = useState(false)
  const text = query.trim()
  const hits = text.length >= 2 && results.query === text ? results.items : []

  useEffect(() => {
    if (text.length < 2) return
    let alive = true
    const timer = window.setTimeout(() => {
      api
        .listProjectSymbols(projectId, { q: text, limit: 8 })
        .then((res) => {
          if (!alive) return
          setResults({ query: text, items: res.items })
          setOpen(true)
        })
        .catch(error => { if (alive) { setResults({ query: text, items: [], error: String(error) }); setOpen(true) } })
    }, 220)
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
  }, [text, projectId])

  const pick = (qualname: string) => {
    onPick(qualname)
    setQuery('')
    setResults({ query: '', items: [] })
    setOpen(false)
  }

  return (
    <div className="relative">
      <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-bg-elevated px-2 py-1">
        <Search size={12} strokeWidth={1.8} className="text-slate-400" />
        <input
          value={query}
          onChange={(event) => { setQuery(event.target.value); setOpen(true) }}
          onFocus={() => text.length >= 2 && setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 120)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && hits[0]) pick(hits[0].qualname)
            if (event.key === 'Escape') setOpen(false)
          }}
          placeholder="搜索函数或类…"
          className="w-40 bg-transparent text-[11px] text-slate-700 outline-none placeholder:text-slate-400"
          aria-label="搜索关系图中心符号"
        />
      </div>
      {open && text.length >= 2 && (
        <ul className="absolute left-0 top-full z-20 mt-1 w-72 overflow-hidden rounded-xl border border-slate-200 bg-bg-elevated py-1 shadow-2">
          {results.query !== text ? <li role="status" className="p-2 text-xs text-slate-400">搜索中…</li> : results.error ? <li role="alert" className="p-2 text-xs text-danger">搜索失败，请重新输入或稍后重试：{results.error}</li> : !hits.length ? <li className="p-2 text-xs text-slate-400">没有找到这个函数或类。</li> : null}
          {hits.map((hit) => (
            <li key={`${hit.qualname}:${hit.path}:${hit.lineno}`}>
              <button
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => pick(hit.qualname)}
                className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left transition-colors hover:bg-accent-soft"
              >
                <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-slate-700">
                  {hit.qualname}
                </span>
                <span className="shrink-0 font-mono text-[9.5px] text-slate-400">
                  {shortPath(hit.path)}:{hit.lineno}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
