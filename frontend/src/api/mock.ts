/**
 * mock 数据层：按契约返回 `public/mock/sample-index.json`（A 线
 * `ci dump-fixture` 产出的**真实解析快照**，非手写假数据）。
 *
 * 快照里没有的东西，mock 只有两选：**派生**（度数、symbol_count、概念标签
 * 从 edges/symbols/concepts 算）或**如实返回空/占位**（源码正文）——不编造。
 * 概念实例与流程由 `frontend/tools/regen_mock.py` 用真引擎检出后并入快照，
 * 概念本体从 `/mock/ontology.json`（B 线 YAML 的 JSON 拍平版）读取。
 */
import { ApiError } from './client'
import type { SseHandler, StreamResult } from './stream'
import type {
  ChangesResponse,
  ConceptDepth,
  ConceptDetail,
  ConceptExplanation,
  ConceptInstance,
  ConceptListItem,
  CreateProjectRequest,
  CreateProjectResponse,
  EdgeKind,
  FileEntry,
  Flow,
  GraphEdge,
  GraphNode,
  GraphQuery,
  GraphResponse,
  HealthResponse,
  ListResponse,
  ProjectDetail,
  ProjectOverview,
  ProjectSummary,
  QueryRequest,
  QueryResponse,
  RelationListResponse,
  RelationRef,
  SseEvent,
  SymbolDetail,
  SymbolListItem,
  SymbolQuery,
  TimelineResponse,
} from './types'

// 快照条目（字段比契约少：mock 负责派生缺的部分，见下）。
interface SnapFile {
  path: string
  language: string
  role: FileEntry['role']
  content_sha256: string
  size_bytes: number
  line_count: number
  in_chunk_index: boolean
}

interface SnapSymbol {
  qualname: string
  name: string
  kind: SymbolListItem['kind']
  path: string
  lineno: number
  end_lineno: number
  header: string
  docstring: string
  n_lines: number
  is_async: boolean
  is_private: boolean
}

interface SnapEdge {
  src_qualname: string
  dst_name: string
  dst_qualname: string | null
  kind: string
  path: string
  lineno: number
  confidence: number
}

/** 概念实例（`frontend/tools/regen_mock.py` 用真引擎检出的数据）。 */
interface SnapConcept {
  concept_id: string
  path: string
  lineno: number
  qualname: string | null
  evidence: string
  confidence: number
}

/** 关键业务流程（A5 检测，同上来源）。 */
interface SnapFlow {
  name: string
  description: string
  entry_qualname: string | null
  steps: Array<{ ordinal: number; qualname: string | null; path: string | null; lineno: number | null; note: string | null }>
}

interface Snapshot {
  project: { id: number; name: string; root_path: string; head_commit: string; head_branch: string }
  files: SnapFile[]
  modules: Array<{ qualname: string; path: string; docstring: string }>
  symbols: SnapSymbol[]
  edges: SnapEdge[]
  concepts: SnapConcept[]
  flows: SnapFlow[]
}

/** 概念本体条目（`/mock/ontology.json`，B 线 YAML 拍平的产物）。 */
export interface MockOntologyConcept {
  concept_id: string
  name: string
  category: string
  summary: string
  principles: string
  tradeoffs: string
  alternatives: string
  references: string[]
}

/** 流式回放的帧间隔。测试里 `setMockStreamDelay(0)` 让回放瞬时完成。 */
let mockStreamDelayMs = 60

export function setMockStreamDelay(ms: number): void {
  mockStreamDelayMs = ms
}

let snapshotPromise: Promise<Snapshot> | null = null

/** 测试注入口：绕过 fetch 直接给快照（node 环境没有相对 URL 可取）。 */
export function provideSnapshot(snapshot: Snapshot): void {
  snapshotPromise = Promise.resolve(snapshot)
  snapEdges = snapshot.edges
}

function loadSnapshot(): Promise<Snapshot> {
  snapshotPromise ??= fetch('/mock/sample-index.json').then((r) => {
    if (!r.ok) throw new Error(`mock 快照加载失败：HTTP ${r.status}`)
    return r.json() as Promise<Snapshot>
  })
  return snapshotPromise
}

let ontologyPromise: Promise<Record<string, MockOntologyConcept>> | null = null
let ontologyOverride: Record<string, MockOntologyConcept> | null = null

/** 测试注入口：直接给本体表。 */
export function provideOntology(map: Record<string, MockOntologyConcept>): void {
  ontologyOverride = map
}

function loadOntology(): Promise<Record<string, MockOntologyConcept>> {
  if (ontologyOverride) return Promise.resolve(ontologyOverride)
  ontologyPromise ??= fetch('/mock/ontology.json')
    .then((r) => (r.ok ? (r.json() as Promise<Record<string, MockOntologyConcept>>) : {}))
    .catch(() => ({}))
  return ontologyPromise
}

/** 派生索引：一次构建，之后全部查表。 */
interface Derived {
  files: FileEntry[]
  symbols: SymbolListItem[]
  symbolCountByPath: Map<string, number>
  inDegree: Map<string, number>
  outDegree: Map<string, number>
  symbolsByQualname: Map<string, SymbolListItem & SnapSymbol>
}

function derive(snap: Snapshot): Derived {
  // qualname → 概念 id 列表（供符号树挂概念标签）。
  const conceptsByQualname = new Map<string, string[]>()
  for (const c of snap.concepts) {
    if (!c.qualname) continue
    const list = conceptsByQualname.get(c.qualname) ?? []
    if (!list.includes(c.concept_id)) list.push(c.concept_id)
    conceptsByQualname.set(c.qualname, list)
  }

  const symbolCountByPath = new Map<string, number>()
  for (const s of snap.symbols) {
    symbolCountByPath.set(s.path, (symbolCountByPath.get(s.path) ?? 0) + 1)
  }

  // 度只统计能落到具体符号的边（dst_qualname 可解析的 call 边），
  // 与"关系图的度"的定义一致；imports 这类模块级边不算符号的度。
  const inDegree = new Map<string, number>()
  const outDegree = new Map<string, number>()
  for (const e of snap.edges) {
    if (e.kind !== 'call' || !e.dst_qualname) continue
    outDegree.set(e.src_qualname, (outDegree.get(e.src_qualname) ?? 0) + 1)
    inDegree.set(e.dst_qualname, (inDegree.get(e.dst_qualname) ?? 0) + 1)
  }

  const symbols: SymbolListItem[] = snap.symbols.map((s, i) => ({
    ...s,
    // 快照没有数据库自增 id：用序号做 mock 内稳定标识（右栏按 qualname 取，
    // id 只是契约形状要求）。
    id: i + 1,
    // 快照没有 dunder/concept 标记：dunder 可从名字客观推出，概念留空
    //（快照本就没有概念实例，填了才是编造）。
    is_dunder: s.name.startsWith('__') && s.name.endsWith('__'),
    in_degree: inDegree.get(s.qualname) ?? 0,
    out_degree: outDegree.get(s.qualname) ?? 0,
    // 概念标签从实例派生（快照的 concepts 是真检测结果）。
    concept_ids: conceptsByQualname.get(s.qualname) ?? [],
  }))

  const symbolsByQualname = new Map<string, SymbolListItem & SnapSymbol>()
  for (let i = 0; i < symbols.length; i++) {
    symbolsByQualname.set(symbols[i].qualname, { ...symbols[i], ...snap.symbols[i] })
  }

  const files: FileEntry[] = snap.files.map((f) => ({
    path: f.path,
    language: f.language,
    role: f.role,
    content_sha256: f.content_sha256,
    size_bytes: f.size_bytes,
    line_count: f.line_count,
    symbol_count: symbolCountByPath.get(f.path) ?? 0,
  }))

  return { files, symbols, symbolCountByPath, inDegree, outDegree, symbolsByQualname }
}

const delay = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

/** 挑一个"有戏"的符号做对话回放主角：行数最大的函数/方法。 */
function pickHeroSymbol(d: Derived): SymbolListItem & SnapSymbol {
  let best = d.symbolsByQualname.get(d.symbols[0].qualname)!
  for (const s of d.symbols) {
    const isCallable = s.kind === 'function' || s.kind === 'method'
    if (isCallable && s.n_lines > best.n_lines) best = d.symbolsByQualname.get(s.qualname)!
  }
  return best
}

function mockSymbolDetail(d: Derived, qualname: string): SymbolDetail {
  const s = d.symbolsByQualname.get(qualname)
  if (!s) {
    throw new ApiError({
      code: 'symbol_not_found',
      title: '符号不存在',
      hint: '换一个 qualname，或先在符号树里确认它存在',
      detail: `qualname=${qualname}`,
      status: 404,
    })
  }

  const toRef = (e: SnapEdge): RelationRef => ({
    qualname: e.src_qualname === qualname ? e.dst_qualname ?? e.dst_name : e.src_qualname,
    path: e.path,
    lineno: e.lineno,
    confidence: e.confidence,
    uncertain: e.confidence < 1,
    note: e.confidence < 1 ? '动态调用，静态分析不确定' : null,
  })

  const callers = d.symbolsByQualname.has(qualname)
    ? snapEdgesOf(qualname, 'dst', 'call').map(toRef)
    : []
  const callees = snapEdgesOf(qualname, 'src', 'call').map(toRef)
  const references = snapEdgesOf(qualname, 'dst', 'references').map(toRef)

  return {
    ...s,
    callers,
    callees,
    references,
    // 快照不含源码正文：如实的占位，标清楚是 mock，不冒充真代码。
    source: `${s.lineno} | ${s.header || s.name}\n${s.docstring ? `${s.lineno + 1} | """${s.docstring.split('\n').join(' ')}"""` : ''}\n(mock：快照未携带源码正文)`,
  }
}

// edges 在快照加载后缓存，供 mockSymbolDetail 查。
let snapEdges: SnapEdge[] = []

function snapEdgesOf(qualname: string, side: 'src' | 'dst', kind: string): SnapEdge[] {
  const key = side === 'src' ? 'src_qualname' : 'dst_qualname'
  return snapEdges.filter((e) => e.kind === kind && e[key] === qualname)
}

// ─── 关系图（契约 §4.5）：从同一条边表派生，形状与后端一致 ────

const MOCK_GRAPH_KINDS = new Set<EdgeKind>(['call', 'inherits', 'decorator', 'references'])

function mockGraph(d: Derived, snap: Snapshot, query: GraphQuery): GraphResponse {
  const allowed = new Set<EdgeKind>(
    query.kinds && query.kinds.length > 0 ? query.kinds : [...MOCK_GRAPH_KINDS],
  )
  const edges: GraphEdge[] = []
  const seen = new Set<string>()
  for (const e of snap.edges) {
    const kind = e.kind as EdgeKind
    if (!MOCK_GRAPH_KINDS.has(kind) || !allowed.has(kind) || !e.dst_qualname) continue
    const src = d.symbolsByQualname.get(e.src_qualname)
    const dst = d.symbolsByQualname.get(e.dst_qualname)
    if (!src || !dst || src.id === dst.id) continue
    const key = `${src.id}:${dst.id}:${kind}`
    if (seen.has(key)) continue
    seen.add(key)
    edges.push({
      src: src.id,
      dst: dst.id,
      kind,
      lineno: e.lineno,
      confidence: e.confidence,
      uncertain: e.confidence < 1,
    })
  }

  const depthLimit = Math.min(Math.max(query.depth ?? 2, 1), 3)
  const maxNodes = Math.min(Math.max(query.max_nodes ?? 80, 1), 200)
  const depths = new Map<number, number | null>()
  let selected: number[]
  let truncated = false
  let center: GraphResponse['center'] = null

  if (query.qualname) {
    const sym = d.symbolsByQualname.get(query.qualname)
    if (!sym) {
      throw new ApiError({
        code: 'symbol_not_found',
        title: '符号不存在',
        hint: '换一个 qualname，或先在符号树里确认它存在',
        detail: `qualname=${query.qualname}`,
        status: 404,
      })
    }
    center = { qualname: sym.qualname, path: sym.path, lineno: sym.lineno }
    selected = [sym.id]
    depths.set(sym.id, 0)
    let frontier = [sym.id]
    for (let level = 0; level < depthLimit && frontier.length > 0; level++) {
      const current = new Set(frontier)
      const next: number[] = []
      for (const edge of edges) {
        const neighbor = current.has(edge.src)
          ? edge.dst
          : current.has(edge.dst)
            ? edge.src
            : null
        if (neighbor === null || depths.has(neighbor)) continue
        if (selected.length >= maxNodes) {
          truncated = true
          continue
        }
        depths.set(neighbor, level + 1)
        selected.push(neighbor)
        next.push(neighbor)
      }
      frontier = next
    }
  } else {
    // 概览：与后端同一条口径——调用度最高的公开函数/类。
    const hubs = d.symbols
      .filter((s) => ['function', 'method', 'class'].includes(s.kind) && !s.is_private)
      .sort(
        (a, b) =>
          b.in_degree + b.out_degree - (a.in_degree + a.out_degree) ||
          a.qualname.localeCompare(b.qualname),
      )
    truncated = hubs.length > maxNodes
    selected = hubs.slice(0, maxNodes).map((s) => s.id)
    for (const id of selected) depths.set(id, null)
  }

  const byId = new Map(d.symbols.map((s) => [s.id, s]))
  const selectedSet = new Set(selected)
  const nodes: GraphNode[] = selected.flatMap((id) => {
    const s = byId.get(id)
    if (!s) return []
    return [
      {
        id: s.id,
        qualname: s.qualname,
        name: s.name,
        kind: s.kind,
        path: s.path,
        lineno: s.lineno,
        end_lineno: s.end_lineno,
        is_async: s.is_async,
        is_private: s.is_private,
        in_degree: s.in_degree,
        out_degree: s.out_degree,
        concept_ids: s.concept_ids,
        depth: depths.get(id) ?? null,
      },
    ]
  })
  return {
    mode: center ? 'focus' : 'overview',
    center,
    depth: center ? depthLimit : null,
    kinds: [...allowed],
    nodes,
    edges: edges.filter((e) => selectedSet.has(e.src) && selectedSet.has(e.dst)),
    truncated,
  }
}

// ─── 对话回放：事件全部取自真实快照数据 ───────────────────────

function buildReplay(d: Derived, snap: Snapshot, question: string): SseEvent[] {
  const hero = pickHeroSymbol(d)
  const heroConcepts = snap.concepts
    .filter((c) => c.qualname === hero.qualname)
    .map((c) => c.concept_id)
  const heroSnippet = hero.header || `def ${hero.name}(...)`
  const callerEdge = snapEdgesOf(hero.qualname, 'dst', 'call')[0]
  const secondSymbol = callerEdge ? d.symbolsByQualname.get(callerEdge.src_qualname) : undefined

  const narrative = [
    `我先看这个问题相关的代码结构。`,
    `规模最大的业务函数是 ${hero.qualname}（${hero.n_lines} 行，`,
    `定义在 ${hero.path}:${hero.lineno}），`,
    secondSymbol
      ? `它被 ${secondSymbol.qualname} 等符号调用，处于链路中段。`
      : `快照中暂未发现它的调用者。`,
    `右栏的证据面板给出了对应位置，点击可跳转查看。`,
  ]

  const events: SseEvent[] = [
    {
      event: 'meta',
      data: {
        task_id: `mock-${Date.now().toString(36)}`,
        conversation_id: `mock-conv-${new Date().toISOString().slice(0, 10)}`,
        model: 'mock-replay',
        tools: [
          'search_code', 'find_symbol', 'read_file', 'get_callers', 'get_callees',
          'list_concepts', 'explain_concept', 'find_concept_instances', 'get_flow',
          'get_changes', 'get_design_decisions', 'get_module_overview',
        ],
      },
    },
    { event: 'tool', data: { name: 'search_code', status: 'running', summary: `搜索「${question.slice(0, 18)}」` } },
    { event: 'tool', data: { name: 'search_code', status: 'ok', summary: `命中 ${secondSymbol ? 2 : 1} 条证据` } },
    {
      event: 'evidence',
      data: {
        path: hero.path,
        lineno: hero.lineno,
        end_lineno: hero.end_lineno,
        qualname: hero.qualname,
        snippet: heroSnippet,
        lanes: ['symbol'],
        concepts: heroConcepts,
      },
    },
  ]
  if (secondSymbol) {
    events.push({
      event: 'evidence',
      data: {
        path: secondSymbol.path,
        lineno: secondSymbol.lineno,
        end_lineno: secondSymbol.end_lineno,
        qualname: secondSymbol.qualname,
        snippet: secondSymbol.header || `def ${secondSymbol.name}(...)`,
        lanes: ['bm25'],
        concepts: [],
      },
    })
  }
  events.push({ event: 'tool', data: { name: 'get_callers', status: 'running', summary: `查 ${hero.name} 的调用者` } })
  events.push({ event: 'tool', data: { name: 'get_callers', status: 'ok', summary: `找到 ${hero.in_degree} 个调用点` } })
  for (const text of narrative) events.push({ event: 'delta', data: { text } })
  events.push({
    event: 'answer',
    data: {
      facts: [
        {
          text: `${hero.qualname} 定义于 ${hero.path}:${hero.lineno}，共 ${hero.n_lines} 行`,
          citation: {
            path: hero.path,
            lineno: hero.lineno,
            end_lineno: hero.end_lineno,
            qualname: hero.qualname,
            snippet: heroSnippet,
          },
        },
        ...(secondSymbol
          ? [
              {
                text: `它被 ${secondSymbol.qualname} 调用（入度 ${hero.in_degree}）`,
                citation: {
                  path: secondSymbol.path,
                  lineno: secondSymbol.lineno,
                  end_lineno: secondSymbol.end_lineno,
                  qualname: secondSymbol.qualname,
                  snippet: secondSymbol.header || `def ${secondSymbol.name}(...)`,
                },
              },
            ]
          : []),
      ],
      inferences: [
        { text: '从行数与调用关系看，它大概率是该模块的核心编排函数（推断，非事实）', confidence: 0.6 },
      ],
      citations: [],
      abstained: false,
      reason: '',
      incomplete: false,
    },
  })
  events.push({ event: 'done', data: { abstained: false, reason: '' } })
  return events
}

/** mock 版流式问答：把回放事件按间隔喂给 onEvent，形状与真流完全一致。 */
export async function mockStreamQuery(
  request: QueryRequest,
  onEvent: SseHandler,
  signal?: AbortSignal,
): Promise<StreamResult> {
  void request
  const snap = await loadSnapshot()
  snapEdges = snap.edges
  const d = derive(snap)
  for (const event of buildReplay(d, snap, request.question)) {
    if (signal?.aborted) return { aborted: true }
    if (mockStreamDelayMs > 0) await delay(mockStreamDelayMs)
    onEvent(event)
  }
  return { aborted: false }
}

// ─── 与真实 API 同形的接口实现 ────────────────────────────────

async function withDerived<T>(fn: (d: Derived, snap: Snapshot) => T): Promise<T> {
  const snap = await loadSnapshot()
  snapEdges = snap.edges
  return fn(derive(snap), snap)
}

export const mockApi = {
  async getHealth(): Promise<HealthResponse> {
    return {
      status: 'ok',
      version: '0.0.0-mock',
      db_path: '(mock：无索引库)',
      db_exists: false,
      schema_applied: false,
      projects: 1,
    }
  },

  async listProjects(): Promise<ProjectSummary[]> {
    return withDerived((d, snap) => {
      const indexedAt = '2026-10-24T08:31:05Z'
      const common = {
        id: snap.project.id,
        name: snap.project.name,
        root_path: snap.project.root_path,
        head_commit: snap.project.head_commit,
        head_branch: snap.project.head_branch,
        indexed_at: indexedAt,
        index_epoch: 1,
        files: d.files.length,
        symbols: d.symbols.length,
        chunks: 0,
      }
      return [common]
    })
  },

  async createProject(req: CreateProjectRequest): Promise<CreateProjectResponse> {
    // mock 模式不支持建索引：返回 502 形状的错误，提示切真实模式。
    void req
    throw new ApiError({
      code: 'bad_request',
      title: 'mock 模式不支持导入项目',
      hint: '设 VITE_CI_MOCK=0 并启动后端（端口 8020）后再试',
      detail: '',
      status: 400,
    })
  },

  async getProject(id: number): Promise<ProjectDetail> {
    return withDerived((d, snap) => ({
      id: snap.project.id,
      name: snap.project.name,
      root_path: snap.project.root_path,
      status: 'ready' as const,
      head_commit: snap.project.head_commit,
      head_branch: snap.project.head_branch,
      indexed_at: '2026-10-24T08:31:05Z',
      index_epoch: 1,
      files: d.files.length,
      symbols: d.symbols.length,
      chunks: 0,
      edges: snap.edges.length,
      concepts: 0,
      concept_instances: 0,
    })).then((detail) => {
      if (detail.id !== id) {
        throw new ApiError({
          code: 'project_not_found',
          title: '项目不存在',
          hint: 'mock 快照里只有项目 1',
          detail: `project_id=${id}`,
          status: 404,
        })
      }
      return detail
    })
  },

  async getProjectOverview(id: number): Promise<ProjectOverview> {
    void id
    return withDerived((d, snap) => {
      const languages = new Map<string, { files: number; lines: number }>()
      for (const f of d.files) {
        const entry = languages.get(f.language) ?? { files: 0, lines: 0 }
        entry.files += 1
        entry.lines += f.line_count
        languages.set(f.language, entry)
      }
      // 入口识别走客观规则：约定俗成的入口文件名。
      const entryFiles = d.files.filter((f) => {
        const base = f.path.split('/').pop() ?? ''
        return ['main.py', 'app.py', '__main__.py'].includes(base)
      })
      const coreModules = [...snap.modules]
        .map((m) => ({
          qualname: m.qualname,
          path: m.path,
          responsibility: m.docstring.split('\n')[0]?.slice(0, 60) || '',
          docstring: m.docstring,
          is_core: true,
          out_degree: 0,
          in_degree: 0,
        }))
        .slice(0, 20)
      return {
        project_id: snap.project.id,
        // 摘要是模板拼接，但每个数字都来自快照——契约 §3.5 的要求。
        architecture_summary:
          `${snap.project.name}@${snap.project.head_branch}：${d.files.length} 个文件、` +
          `${d.symbols.length} 个符号、${snap.edges.length} 条关系边。` +
          `（mock：完整概览由 M2 的 /overview 端点提供）`,
        languages: [...languages.entries()]
          .map(([language, v]) => ({ language, files: v.files, lines: v.lines }))
          .sort((a, b) => b.files - a.files),
        frameworks: [],
        entry_points: entryFiles.map((f) => ({
          kind: 'file' as const,
          target: f.path,
          source_path: f.path,
          doc: null,
        })),
        core_modules: coreModules,
        dependencies: [],
        stats: {
          files: d.files.length,
          python_files: d.files.filter((f) => f.language === 'python').length,
          symbols: d.symbols.length,
          edges: snap.edges.length,
          concepts: 0,
          flows: 0,
        },
      }
    })
  },

  async getProjectFiles(id: number): Promise<FileEntry[]> {
    void id
    return withDerived((d) => d.files)
  },

  async listProjectSymbols(id: number, query: SymbolQuery = {}): Promise<ListResponse<SymbolListItem>> {
    void id
    return withDerived((d) => {
      const q = query.q?.toLowerCase()
      let items = d.symbols.filter((s) => {
        if (query.kind && s.kind !== query.kind) return false
        if (query.path && !s.path.startsWith(query.path)) return false
        if (q) {
          const hay = `${s.qualname} ${s.name} ${s.docstring ?? ''}`.toLowerCase()
          if (!hay.includes(q)) return false
        }
        return true
      })
      items = [...items].sort((a, b) => a.path.localeCompare(b.path) || a.lineno - b.lineno)
      const total = items.length
      const offset = query.offset ?? 0
      const limit = query.limit ?? 50
      return { items: items.slice(offset, offset + limit), total }
    })
  },

  async getSymbol(id: number, qualname: string): Promise<SymbolDetail> {
    void id
    return withDerived((d) => mockSymbolDetail(d, qualname))
  },

  async getSymbolCallers(id: number, qualname: string): Promise<RelationListResponse> {
    void id
    return withDerived((d) => {
      const items = mockSymbolDetail(d, qualname).callers
      return { items, total: items.length }
    })
  },

  async getSymbolCallees(id: number, qualname: string): Promise<RelationListResponse> {
    void id
    return withDerived((d) => {
      const items = mockSymbolDetail(d, qualname).callees
      return { items, total: items.length }
    })
  },

  async listFlows(id: number): Promise<ListResponse<Flow>> {
    void id
    // 流程由 regen_mock.py 从真索引检出（步骤跨取样模块，qualname 是
    // 真实线索；文件列表全量，path 均可导航）。
    const snap = await loadSnapshot()
    const items: Flow[] = snap.flows.map((f, i) => ({
      id: i + 1,
      name: f.name,
      description: f.description,
      entry_qualname: f.entry_qualname ?? '',
      steps: f.steps.map((st) => ({
        ordinal: st.ordinal,
        qualname: st.qualname ?? '',
        path: st.path ?? '',
        lineno: st.lineno ?? 0,
        note: st.note,
      })),
    }))
    return { items, total: items.length }
  },

  async getGraph(id: number, query: GraphQuery = {}): Promise<GraphResponse> {
    void id
    return withDerived((d, snap) => mockGraph(d, snap, query))
  },

  async getTimeline(id: number, limit = 30): Promise<TimelineResponse> {
    void id
    void limit
    // 快照只对应一次全量索引：如实给一格，不编造历史。
    return withDerived((d, snap) => ({
      head: snap.project.head_commit,
      total: 1,
      items: [
        {
          id: 'run-mock',
          kind: 'index' as const,
          mode: 'full' as const,
          ok: true,
          at: '2026-10-24T08:31:05Z',
          base_commit: null,
          head_commit: snap.project.head_commit,
          summary: `全量索引：${d.files.length} 个文件、${d.symbols.length} 个符号（mock 快照）`,
          files: {
            added: null,
            modified: null,
            deleted: null,
            total: d.files.length,
          },
          symbols_changed: null,
          symbols_added: d.symbols.length,
          symbols_removed: null,
          files_total: d.files.length,
          source: null,
          stale_design_decisions: [],
        },
      ],
    }))
  },

  async getChanges(id: number, since?: string): Promise<ChangesResponse> {
    void id
    void since
    // 契约 §7.1：M1–M5 期间返回空壳，字段不删不改。
    return {
      since: since ?? '',
      head: '',
      summary: '',
      files: { added: [], modified: [], deleted: [] },
      changed_symbols: [],
      impacted: { modules: [], symbols: [], concept_ids: [] },
      tests: [],
      stale_design_decisions: [],
    }
  },

  // ─── 概念：快照的 concepts 由 frontend/tools/regen_mock.py 用真引擎检出 ──

  async listConcepts(projectId: number, filter: { q?: string; category?: string } = {}): Promise<ListResponse<ConceptListItem>> {
    void projectId
    const [snap, ontology] = await Promise.all([loadSnapshot(), loadOntology()])
    snapEdges = snap.edges
    const byId = new Map<string, SnapConcept[]>()
    for (const c of snap.concepts) {
      const list = byId.get(c.concept_id) ?? []
      list.push(c)
      byId.set(c.concept_id, list)
    }
    const q = filter.q?.toLowerCase()
    const items: ConceptListItem[] = [...byId.entries()]
      .flatMap(([id, instances]): ConceptListItem[] => {
        const o = ontology[id]
        const name = o?.name ?? id
        const summary = o?.summary ?? ''
        if (q && !`${id} ${name} ${summary}`.toLowerCase().includes(q)) return []
        if (filter.category && (o?.category ?? 'other') !== filter.category) return []
        return [
          {
            concept_id: id,
            name,
            category: (o?.category ?? 'other') as ConceptListItem['category'],
            summary,
            instance_count: instances.length,
            first_instance_path: instances[0]?.path ?? null,
          },
        ]
      })
      .sort((a, b) => b.instance_count - a.instance_count)
    return { items, total: items.length }
  },

  async getConcept(projectId: number, conceptId: string): Promise<ConceptDetail> {
    void projectId
    const [snap, ontology] = await Promise.all([loadSnapshot(), loadOntology()])
    const instances = snap.concepts.filter((c) => c.concept_id === conceptId)
    const o = ontology[conceptId]
    if (instances.length === 0 && !o) {
      throw new ApiError({
        code: 'concept_not_found',
        title: '概念不存在',
        hint: '快照里没有这个概念的实例，本体里也没有定义',
        detail: `concept_id=${conceptId}`,
        status: 404,
      })
    }
    return {
      concept_id: conceptId,
      name: o?.name ?? conceptId,
      category: (o?.category ?? 'other') as ConceptDetail['category'],
      summary: o?.summary ?? '',
      principles: o?.principles ?? '',
      tradeoffs: o?.tradeoffs ?? '',
      alternatives: o?.alternatives ?? '',
      references: o?.references ?? [],
      instance_count: instances.length,
      instance_paths: [...new Set(instances.map((c) => c.path))].sort(),
    }
  },

  async listConceptInstances(projectId: number, conceptId: string): Promise<ListResponse<ConceptInstance>> {
    void projectId
    const snap = await loadSnapshot()
    snapEdges = snap.edges
    const d = derive(snap)
    const rows = snap.concepts
      .map((c, i) => ({ c, i }))
      .filter(({ c }) => c.concept_id === conceptId)
    if (rows.length === 0) {
      throw new ApiError({
        code: 'concept_not_found',
        title: '概念不存在',
        hint: '快照里没有这个概念的实例',
        detail: `concept_id=${conceptId}`,
        status: 404,
      })
    }
    const items: ConceptInstance[] = rows.map(({ c, i }) => ({
      id: i + 1,
      concept_id: c.concept_id,
      path: c.path,
      lineno: c.lineno,
      qualname: c.qualname,
      symbol_id: c.qualname ? d.symbolsByQualname.get(c.qualname)?.id ?? null : null,
      evidence: c.evidence,
      confidence: c.confidence,
      snippet: c.qualname ? d.symbolsByQualname.get(c.qualname)?.header ?? '' : '',
    }))
    return { items, total: items.length }
  },

  async explainConcept(
    projectId: number,
    conceptId: string,
    depth: ConceptDepth,
  ): Promise<ConceptExplanation> {
    void projectId
    // 与后端 knowledge.py 同一套语义：quick 读本体、project 从实例派生、
    // deep 依赖 LLM（mock 不装）。
    const [snap, ontology] = await Promise.all([loadSnapshot(), loadOntology()])
    const instances = snap.concepts.filter((c) => c.concept_id === conceptId)
    const o = ontology[conceptId]
    if (instances.length === 0 && !o) {
      throw new ApiError({
        code: 'concept_not_found',
        title: '概念不存在',
        hint: '快照里没有这个概念的实例，本体里也没有定义',
        detail: `concept_id=${conceptId}`,
        status: 404,
      })
    }
    const items: ConceptInstance[] = instances.map((c, i) => ({
      id: i + 1,
      concept_id: c.concept_id,
      path: c.path,
      lineno: c.lineno,
      qualname: c.qualname,
      symbol_id: null,
      evidence: c.evidence,
      confidence: c.confidence,
      snippet: '',
    }))
    if (depth === 'deep') {
      throw new ApiError({
        code: 'upstream_error',
        title: '深度解释暂不可用',
        hint: 'deep 依赖 LLM Provider；quick 与 project 现在可用',
        detail: 'mock replay has no llm',
        status: 502,
      })
    }
    if (depth === 'quick') {
      return {
        concept_id: conceptId,
        depth: 'quick',
        summary: o?.summary ?? '',
        facts: [],
        inferences: [],
        instances: items,
        llm_used: false,
      }
    }
    return {
      concept_id: conceptId,
      depth: 'project',
      summary: o?.summary ?? '',
      facts: items.map((inst) => ({
        text: `${inst.evidence}（${inst.path}:${inst.lineno}）`,
        citation: { path: inst.path, lineno: inst.lineno, end_lineno: inst.lineno, qualname: inst.qualname, snippet: '' },
      })),
      inferences: [],
      instances: items,
      llm_used: false,
    }
  },

  async query(request: QueryRequest): Promise<QueryResponse> {
    void request
    // 非流式在 mock 下复用回放的最终帧：把 stream 跑完取 answer。
    let final: QueryResponse | null = null
    await mockStreamQuery(request, (event) => {
      if (event.event === 'delta') return
      if (event.event === 'answer') {
        final = {
          text: '',
          facts: event.data.facts,
          inferences: event.data.inferences,
          citations: event.data.citations,
          tools_used: ['search_code', 'get_callers'],
          abstained: event.data.abstained,
          abstention_reason: event.data.reason,
          // 从事件透传：mock 回放当前恒为 false，但不能在这里写死——
          // 将来回放一个「未完成」样例时，非流式路径要和流式一致。
          incomplete: event.data.incomplete,
          evidence: [],
        }
      }
    })
    return final ?? {
      text: '',
      facts: [],
      inferences: [],
      citations: [],
      tools_used: [],
      abstained: true,
      abstention_reason: 'mock 回放未产出答案',
      incomplete: false,
      evidence: [],
    }
  },

  streamQuery: mockStreamQuery,
}
