/**
 * CodeInsight 前端类型定义 · 冻结
 *
 * 与 `docs/api-contract.md` **一一对应**。改动必须先走 `docs/requests/` 流程，
 * 由 A 线同时改契约与本文件。
 *
 * 约定：
 * - 字段名沿用后端的 snake_case，**不做 camelCase 转换**（少一层映射，少一处错）。
 * - 联合类型用 `as const` 数组 + 派生类型，保证与后端枚举一致。
 */

// ─────────────────────────────────────────────────────────────
// 枚举
// ─────────────────────────────────────────────────────────────

export const SYMBOL_KINDS = [
  'module',
  'class',
  'function',
  'method',
  'property',
  'constant',
] as const
export type SymbolKind = (typeof SYMBOL_KINDS)[number]

export const EDGE_KINDS = [
  'call',
  'inherits',
  'imports',
  'decorator',
  'references',
  'returns',
] as const
export type EdgeKind = (typeof EDGE_KINDS)[number]

/** 关系图默认展开的边（契约 §4.5）。`imports` 是模块级边，默认不画。 */
export const GRAPH_EDGE_KINDS = ['call', 'inherits', 'decorator', 'references'] as const
export type GraphEdgeKind = (typeof GRAPH_EDGE_KINDS)[number]

export const CONCEPT_DEPTHS = ['quick', 'project', 'deep'] as const
export type ConceptDepth = (typeof CONCEPT_DEPTHS)[number]

export const FILE_ROLES = [
  'source',
  'test',
  'vendored',
  'generated',
  'config',
  'doc',
] as const
export type FileRole = (typeof FILE_ROLES)[number]

export const CONCEPT_CATEGORIES = [
  'auth',
  'cache',
  'db',
  'concurrency',
  'async',
  'http',
  'config',
  'pattern',
  'data-structure',
  'security',
  'observability',
  'testing',
  'build',
  'other',
] as const
export type ConceptCategory = (typeof CONCEPT_CATEGORIES)[number]

export const RETRIEVAL_LANES = ['bm25', 'dense', 'symbol', 'concept', 'neighbor'] as const
export type RetrievalLane = (typeof RETRIEVAL_LANES)[number]

export const TOOL_STATUSES = ['running', 'ok', 'error'] as const
export type ToolStatus = (typeof TOOL_STATUSES)[number]

export const INDEX_MODES = ['full', 'incremental'] as const
export type IndexMode = (typeof INDEX_MODES)[number]

export const PROJECT_STATUSES = ['indexing', 'ready', 'failed', 'stale'] as const
export type ProjectStatus = (typeof PROJECT_STATUSES)[number]

// ─────────────────────────────────────────────────────────────
// 通用
// ─────────────────────────────────────────────────────────────

/** 错误响应体。全站只有这一个错误变体（契约 §0.3）。 */
export interface ApiErrorBody {
  error: {
    code: string
    title: string
    hint: string
    detail: string
  }
}

/** 错误码全集。未知 code 按 `internal_error` 兜底，不要白屏。 */
export type ApiErrorCode =
  | 'bad_request'
  | 'project_not_found'
  | 'symbol_not_found'
  | 'concept_not_found'
  | 'not_indexed'
  | 'index_running'
  | 'upstream_error'
  | 'timeout'
  | 'internal_error'

/** 列表响应统一形状（契约 §0.4）。 */
export interface ListResponse<T> {
  items: T[]
  total: number
}

/** 一条指向代码的引用。`path:lineno` 是本项目的核心承诺。 */
export interface Citation {
  path: string
  lineno: number
  end_lineno: number
  qualname: string | null
  snippet: string
}

/** 一条可验证的代码事实。每条 fact 必须带 citation。 */
export interface Fact {
  text: string
  citation: Citation
}

/** 一条模型推断。显式标注，不可与 facts 混渲染。 */
export interface Inference {
  text: string
  confidence: number
}

/** 检索到的一条证据。 */
export interface Evidence {
  chunk_id: number
  path: string
  lineno: number
  end_lineno: number
  qualname: string | null
  snippet: string
  score: number
  lanes: RetrievalLane[]
  concept_ids: string[]
}

/** 关系图上的一条边引用（调用者 / 被调者 / 引用处）。 */
export interface RelationRef {
  qualname: string
  path: string
  lineno: number
  confidence: number
  uncertain?: boolean
  note?: string | null
}

// ─────────────────────────────────────────────────────────────
// 健康检查 / 项目
// ─────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string
  version: string
  db_path: string
  db_exists: boolean
  schema_applied: boolean
  projects: number
}

/** `GET /projects` 列表项（契约 §3.2）。 */
export interface ProjectSummary {
  id: number
  name: string
  root_path: string
  head_commit: string | null
  head_branch: string | null
  indexed_at: string | null
  index_epoch: number
  files: number
  symbols: number
  chunks: number
}

/** `POST /projects` 请求体（契约 §3.3）。 */
export interface CreateProjectRequest {
  root_path: string
  ref?: string
  name?: string
}

/** `POST /projects` 响应（202）。 */
export interface CreateProjectResponse {
  id: number
  name: string
  root_path: string
  status: 'indexing'
  head_commit: string | null
  head_branch: string | null
}

/** `GET /projects/{id}` 响应（契约 §3.4）。 */
export interface ProjectDetail extends ProjectSummary {
  status: ProjectStatus
  edges: number
  concepts: number
  concept_instances: number
}

/** `GET /projects/{id}/overview` 响应（契约 §3.5）。 */
export interface ProjectOverview {
  project_id: number
  architecture_summary: string
  languages: Array<{ language: string; files: number; lines: number }>
  frameworks: string[]
  entry_points: EntryPoint[]
  core_modules: CoreModule[]
  dependencies: Dependency[]
  stats: ProjectStats
}

export interface EntryPoint {
  kind: 'file' | 'console_script' | 'framework_app'
  target: string
  source_path: string | null
  doc: string | null
}

export interface CoreModule {
  qualname: string
  path: string
  responsibility: string | null
  docstring: string | null
  is_core: boolean
  out_degree: number
  in_degree: number
}

export interface Dependency {
  name: string
  version: string
  source: 'pyproject' | 'requirements' | 'import'
  declared: boolean
}

export interface ProjectStats {
  files: number
  python_files: number
  symbols: number
  edges: number
  concepts: number
  flows: number
}

/** `GET /projects/{id}/files` 返回裸数组（契约 §3.6）。 */
export interface FileEntry {
  path: string
  language: string
  role: FileRole
  content_sha256: string
  size_bytes: number
  line_count: number
  symbol_count: number
}

// ─────────────────────────────────────────────────────────────
// 符号
// ─────────────────────────────────────────────────────────────

/** 符号列表项与详情共用的字段（契约 §4.1 / §4.2）。 */
export interface SymbolBase {
  id: number
  qualname: string
  name: string
  kind: SymbolKind
  path: string
  lineno: number
  end_lineno: number
  header: string | null
  docstring: string | null
  n_lines: number
  is_async: boolean
  is_private: boolean
  is_dunder: boolean
  in_degree: number
  out_degree: number
  concept_ids: string[]
}

export interface SymbolListItem extends SymbolBase {}

export interface SymbolDetail extends SymbolBase {
  callers: RelationRef[]
  callees: RelationRef[]
  references: RelationRef[]
  source: string
  /** 同名多义时为 true（契约 §4.2）。 */
  ambiguous?: boolean
  alternatives?: Array<{ qualname: string; path: string; lineno: number }>
}

/** `GET .../symbols` 查询参数（契约 §4.1）。 */
export interface SymbolQuery {
  q?: string
  kind?: SymbolKind
  path?: string
  limit?: number
  offset?: number
}

/** `GET .../callers` / `callees` 响应（契约 §4.3）。 */
export interface RelationListResponse extends ListResponse<RelationRef> {}

// ─────────────────────────────────────────────────────────────
// 关系图（契约 §4.5）
// ─────────────────────────────────────────────────────────────

export interface GraphNode {
  id: number
  qualname: string
  name: string
  kind: SymbolKind
  path: string
  lineno: number
  end_lineno: number
  is_async: boolean
  is_private: boolean
  in_degree: number
  out_degree: number
  /** 该符号命中的概念——节点上的概念标签就靠它（源文档 §2.2）。 */
  concept_ids: string[]
  /** 距中心的跳数；概览图为 null。 */
  depth: number | null
}

export interface GraphEdge {
  src: number
  dst: number
  kind: EdgeKind
  lineno: number | null
  confidence: number
  /** `confidence < 1`：动态调用等静态分析定不了的关系。 */
  uncertain: boolean
}

export interface GraphResponse {
  mode: 'focus' | 'overview'
  center: { qualname: string; path: string; lineno: number } | null
  depth: number | null
  kinds: EdgeKind[]
  nodes: GraphNode[]
  edges: GraphEdge[]
  /** 有节点因上限未返回；前端必须显式提示。 */
  truncated: boolean
}

export interface GraphQuery {
  qualname?: string
  depth?: number
  max_nodes?: number
  kinds?: EdgeKind[]
}

// ─────────────────────────────────────────────────────────────
// 流程
// ─────────────────────────────────────────────────────────────

export interface FlowStep {
  ordinal: number
  qualname: string | null
  path: string | null
  lineno: number | null
  note: string | null
}

export interface Flow {
  id: number
  name: string
  description: string | null
  entry_qualname: string | null
  steps: FlowStep[]
}

// ─────────────────────────────────────────────────────────────
// 知识层
// ─────────────────────────────────────────────────────────────

export interface ConceptListItem {
  concept_id: string
  name: string
  category: ConceptCategory
  summary: string
  instance_count: number
  first_instance_path: string | null
}

export interface ConceptDetail {
  learning_targets?: LearningTarget[]
  concept_id: string
  name: string
  category: ConceptCategory
  summary: string
  principles: string | null
  tradeoffs: string | null
  alternatives: string | null
  references: string[]
  instance_count: number
  instance_paths: string[]
}

export interface ConceptInstance {
  id: number
  concept_id: string
  path: string
  lineno: number
  qualname: string | null
  symbol_id: number | null
  /** 命中了哪条检测规则——前端必须显示它。 */
  evidence: string
  confidence: number
  snippet: string
}

/** `POST .../explain` 请求体（契约 §6.4）。 */
export interface ExplainConceptRequest {
  depth: ConceptDepth
}

export interface ConceptExplanation {
  concept_id: string
  depth: ConceptDepth
  summary: string
  facts: Fact[]
  inferences: Inference[]
  instances: ConceptInstance[]
  /** `quick` 级恒为 false（不调 LLM）。 */
  llm_used: boolean
}

// ─────────────────────────────────────────────────────────────
// 变更
// ─────────────────────────────────────────────────────────────

export type SymbolChangeKind =
  | 'added'
  | 'removed'
  | 'signature_changed'
  | 'body_changed'
  | 'docstring_changed'
  | 'moved'

export interface ChangedFile {
  path: string
  status: 'A' | 'M' | 'D' | 'R'
  changed_symbols?: number
}

export interface ChangedSymbol {
  qualname: string
  path: string
  lineno: number
  change: SymbolChangeKind
}

export interface TestOutcome {
  nodeid: string
  outcome: 'passed' | 'failed' | 'skipped' | 'error'
  duration_s: number | null
}

export interface StaleDesignDecision {
  doc_id: string
  title: string
  reason: string
}

/** `GET /projects/{id}/changes` 响应（契约 §7.1）。 */
export interface ChangesResponse {
  since: string | null
  head: string | null
  summary: string
  files: {
    added: ChangedFile[]
    modified: ChangedFile[]
    deleted: ChangedFile[]
  }
  changed_symbols: ChangedSymbol[]
  impacted: {
    modules: string[]
    symbols: Array<{ qualname: string; path: string; lineno: number }>
    concept_ids: string[]
  }
  tests: TestOutcome[]
  stale_design_decisions: StaleDesignDecision[]
}

/** 时间线的一格（契约 §7.2）。全量索引不知道逐状态文件数时为 null，不要当 0。 */
export interface TimelineItem {
  id: string
  kind: 'index' | 'change'
  mode: IndexMode | null
  ok: boolean
  at: string | null
  base_commit: string | null
  head_commit: string | null
  summary: string
  files: {
    added: number | null
    modified: number | null
    deleted: number | null
    total: number
  }
  symbols_changed: number | null
  symbols_added: number | null
  symbols_removed: number | null
  files_total: number | null
  source: string | null
  stale_design_decisions: Array<{ doc_id: string; title: string }>
}

/** `GET /projects/{id}/timeline` 响应（契约 §7.2）。 */
export interface TimelineResponse {
  head: string | null
  total: number
  items: TimelineItem[]
}

// ─────────────────────────────────────────────────────────────
// 问答
// ─────────────────────────────────────────────────────────────

export interface QueryRequest {
  project_id: number
  question: string
  /** 带同一个值 = 连续追问。 */
  conversation_id?: string
  reading_context?: ReadingContext
}

/** `POST /query` 响应（契约 §8.1）。 */
export interface QueryResponse extends KnowledgeAnswerMetadata {
  text: string
  facts: Fact[]
  inferences: Inference[]
  citations: Citation[]
  tools_used: string[]
  abstained: boolean
  abstention_reason: string
  /** 走满轮次/工具上限仍未收尾。true 时要提示「没分析完」，不能当成正常答案。 */
  incomplete: boolean
  evidence: Evidence[]
}

// ─────────────────────────────────────────────────────────────
// SSE 事件（契约 §8.3）
// ─────────────────────────────────────────────────────────────

export interface SseMetaEvent {
  task_id: string
  conversation_id: string
  model: string
  tools: string[]
}

export interface SseDeltaEvent {
  text: string
}

export interface SseToolEvent {
  name: string
  status: ToolStatus
  summary: string
}

export interface SseEvidenceEvent {
  path: string
  lineno: number
  end_lineno: number
  qualname: string | null
  snippet: string
  lanes: RetrievalLane[]
  concepts: string[]
}

export interface SseAnswerEvent extends KnowledgeAnswerMetadata {
  text?: string
  facts: Fact[]
  inferences: Inference[]
  citations: Citation[]
  abstained: boolean
  reason: string
  /** 未收尾（轮次/工具上限）。与 abstained 是两回事。 */
  incomplete: boolean
}

export interface SseErrorEvent {
  code: ApiErrorCode
  title: string
  hint: string
}

export interface SseDoneEvent {
  abstained: boolean
  reason: string
}

/** SSE 事件名全集（契约 §8.3）。 */
export type SseEventName =
  | 'meta'
  | 'delta'
  | 'tool'
  | 'evidence'
  | 'answer'
  | 'error'
  | 'done'

/** 事件名 → data 形状的映射。 */
export interface SseEventMap {
  meta: SseMetaEvent
  delta: SseDeltaEvent
  tool: SseToolEvent
  evidence: SseEvidenceEvent
  answer: SseAnswerEvent
  error: SseErrorEvent
  done: SseDoneEvent
}

export type SseEvent = {
  [K in SseEventName]: { event: K; data: SseEventMap[K] }
}[SseEventName]

/** 请求 0001 的知识扩展；知识来源不能当作项目 Citation。 */
export interface KnowledgeReadingContext {
  kind: 'knowledge'
  topic_id: string
  section_id?: string | null
  version: string
}
export interface CodeReadingContext {
  kind: 'code'
  project_id: number
  path: string
  lineno: number
  end_lineno?: number
}
export type ReadingContext = KnowledgeReadingContext | CodeReadingContext
export interface KnowledgeTopic {
  id: string
  title: string
  summary: string
  group: string
  version: string
  body: string
  sections: Array<{ id: string; title: string; content: string }>
  concept_ids: string[]
  sources: KnowledgeSource[]
  prerequisite_targets: LearningTarget[]
  related_targets: LearningTarget[]
  learning_targets: LearningTarget[]
  dialect: string | null
}
export interface KnowledgeTree {
  version: string
  groups: Array<{ title: string; topics: Array<{ id: string; title: string; summary: string; version: string; href: string }> }>
}
export interface KnowledgeSearch {
  items: KnowledgeHit[]
  total: number
  version: string
}
export interface LearningTarget {
  topic_id: string
  section_id: string | null
  title: string
  version: string
  href: string
}
export interface KnowledgeSource {
  id: string
  title: string
  author: string
  url: string
  version: string
  license: string
  license_url: string
  retrieved_at: string
  sha256: string
  modifications: string
}
export interface KnowledgeHit {
  target: LearningTarget
  snippet: string
  score: number
  sources: KnowledgeSource[]
}
export interface KnowledgeAnswerMetadata {
  knowledge_sources?: KnowledgeHit[]
  learning_entries?: LearningTarget[]
  learning_targets?: LearningTarget[]
  reading_status?: string
  knowledge_error?: string | null
}
