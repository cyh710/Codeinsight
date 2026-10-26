/**
 * 前端状态类型总集（组织法抄织忆：一个项目一个 `types.ts` 集中放）。
 * 与后端交换的形状一律用 `../api/types.ts` 的冻结类型，这里只放**前端视图状态**。
 */
import type {
  Citation,
  Fact,
  Inference,
  RetrievalLane,
  ToolStatus,
  LearningTarget,
  KnowledgeHit,
  ReadingContext,
} from '../api/types'

// ─── 对话 ─────────────────────────────────────────────────────

/** 工具时间线的一行（SSE `tool` 事件的投影）。 */
export interface ToolTimelineItem {
  name: string
  status: ToolStatus
  summary: string
}

/** 右栏证据面板的一格。SSE `evidence` 事件与非流式 `evidence[]` 统一到这里。 */
export interface PanelEvidence {
  path: string
  lineno: number
  end_lineno: number
  qualname: string | null
  snippet: string
  lanes: RetrievalLane[]
  concepts: string[]
  score?: number
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  streaming?: boolean
  timestamp: string
  readingContext?: ReadingContext | null
  requestId?: string
  legacy?: boolean
  sourceHeadCommit?: string | null
  /** 出错时渲染错误卡而不是气泡（code 见契约 §0.3）。 */
  error?: { code: string; title: string; hint: string }
  /** 以下三项只在 assistant 落定后有值（ADR 0007：facts 与 inferences 分栏）。 */
  facts?: Fact[]
  inferences?: Inference[]
  citations?: Citation[]
  abstained?: boolean
  /** 走满轮次上限未完成（契约 §8.3 新增）——与 abstained「没找到」是两回事。 */
  incomplete?: boolean
  abstentionReason?: string
  /** 本轮的工具时间线（边流边长）。 */
  tools?: ToolTimelineItem[]
  /** 本轮积累的证据（边流边长，右栏实时渲染）。 */
  evidence?: PanelEvidence[]
  knowledgeSources?: KnowledgeHit[]
  learningEntries?: LearningTarget[]
  learningTargets?: LearningTarget[]
  knowledgeError?: string | null
  /** 编排执行元数据（契约 §16.2）。识别为开发任务时非空，渲染 ExecutionCard。 */
  execution?: import('../api/types').ExecutionMetadata | null
}

export interface ChatStore {
  projectId: number | null
  currentTitle: string
  currentArchived: boolean
  listLoading: boolean
  draft: string
  error: string
  loading: boolean
  conversations: import('../api/types').Conversation[]
  nextCursor: number | null
  turnsCursor: number | null
  taskId: string | null
  search: string
  allProjects: boolean
  archived: boolean
  find: string
  focusRequest: string | null
  setDraft: (value: string) => void
  setFind: (value: string) => void
  refreshConversations: (more?: boolean) => Promise<void>
  searchConversations: (query: string, all?: boolean, archived?: boolean) => void
  openConversation: (pid: number, cid: string, focusRequest?: string) => Promise<void>
  newConversation: (pid: number) => Promise<void>
  updateConversation: (cid: string, patch: Record<string, unknown>, pid?: number) => Promise<void>
  loadMore: () => Promise<void>
  pollRunning: () => Promise<void>
  restoreQuestion: (message: ChatMessage) => void
  messages: ChatMessage[]
  streaming: boolean
  /** 连续追问用；空串 = 新会话。 */
  conversationId: string
  /** 当前流的中止器（"停止"按钮用）。 */
  _abortController: AbortController | null

  sendMessage: (projectId: number, question: string) => Promise<void>
  stopStreaming: () => void
  reset: () => void
  /**
   * 切到另一个项目：**按项目分别保存会话**，切回来时恢复该项目的对话。
   * 后端会话键是 `project_id:conversation_id`，所以前端也不能串台。
   */
  switchProject: (projectId: number) => Promise<void>
}

// ─── 项目 ─────────────────────────────────────────────────────

export interface IndexActivity {
  projectId: number
  name: string
  phase: 'indexing' | 'syncing' | 'ready' | 'failed' | 'unavailable' | 'paused'
  observedAt: number
  message?: string
  detail?: import('../api/types').ProjectDetail
  request?: import('../api/types').CreateProjectRequest
}

export interface ProjectStore {
  projects: import('../api/types').ProjectSummary[]
  currentProjectId: number | null
  /** 当前项目的详情（含 status 与计数；导入轮询期间实时更新）。 */
  currentDetail: import('../api/types').ProjectDetail | null
  files: import('../api/types').FileEntry[]
  /**
   * 已按文件加载的符号：path → 符号列表。
   *
   * 契约 §0.4 把 `limit` 上限压在 500——一次性拉全量符号拿不到
   * （织忆 688 文件 / 6543 符号），所以改成**展开哪个文件拉哪个**。
   */
  symbolsByPath: Map<string, import('../api/types').SymbolListItem[]>
  /** 正在拉符号的文件（展开时转圈用）。 */
  loadingPaths: Set<string>
  loading: boolean
  error: string
  /** 导入项目进行中（对话框按钮的禁用态与状态行共用）。 */
  importing: boolean
  importError: string
  indexActivities: Record<number, IndexActivity>
  resumeIndexing: (id: number) => void
  dismissIndexActivity: (id: number) => void
  retryIndexing: (id: number) => Promise<void>

  init: () => Promise<void>
  selectProject: (id: number) => Promise<void>
  importProject: (rootPath: string, name?: string, ref?: string) => Promise<void>
  relocateProject: (id: number, rootPath: string) => Promise<boolean>
  /** 展开文件时按需拉它的符号（已拉过则直接返回）。 */
  loadSymbolsForPath: (path: string) => Promise<void>
}

// ─── 工作台（当前选中什么、右栏显示什么） ─────────────────────

/** 右栏形态：证据面板，或概念卡（**右栏替换**，已对齐 C-Q3）。 */
export type RightPanel =
  | { mode: 'evidence'; messageId?: string }
  | { mode: 'symbol'; qualname: string; lineno?: number; version?: string }
  | { mode: 'concept'; conceptId: string }
  | { mode: 'knowledge-tree' }
  | { mode: 'knowledge'; target: LearningTarget }
  | { mode: 'file'; path: string; lineno: number; version?: string }

export interface WorkbenchStore {
  tabs: Array<{ id: string; panel: RightPanel; title: string }>
  activeTab: string
  closedTabs: RightPanel[]
  pinned: boolean
  followEvidence: boolean
  newEvidence: boolean
  readingMode: 'follow' | 'fixed' | 'none'
  indexVersion: string | null
  chatScroll: number | null
  codePositions: Record<string, { scrollTop: number; scrollLeft: number }>
  setChatScroll: (value: number) => void
  saveCodePosition: (key: string, value: { scrollTop: number; scrollLeft: number }) => void
  setIndexVersion: (version: string | null) => void
  activateTab: (id: string) => void
  closeTab: (id: string) => void
  closeOtherTabs: () => void
  reopenTab: () => void
  setPinned: (value: boolean) => void
  setFollowEvidence: (value: boolean) => void
  notifyEvidence: () => void
  openEvidence: (messageId?: string) => void
  openMaterial: (panel: RightPanel) => void
  fixReading: (reading?: ReadingContext) => void
  followReading: () => void
  selectedPath: string | null
  /** 展开的目录（path → true）。 */
  expandedDirs: Record<string, boolean>
  /** 展开了符号列表的文件（path → true）。 */
  expandedFiles: Record<string, boolean>
  treeFilter: string
  rightPanel: RightPanel
  history: Array<{ panel: RightPanel; path: string | null; reading: ReadingContext | null }>
  historyIndex: number
  reading: ReadingContext | null
  scrollPositions: Record<string, number>
  directoryQuery: string
  setDirectoryQuery: (query: string) => void

  selectFile: (path: string, lineno?: number, version?: string | null) => void
  /** `lineno` 定位到符号在文件里的确切行（教材/证据跳回代码时用）。 */
  selectSymbol: (qualname: string, path: string, lineno?: number, version?: string | null) => void
  openConcept: (conceptId: string) => void
  backToEvidence: () => void
  toggleDir: (path: string) => void
  toggleFile: (path: string) => void
  setTreeFilter: (q: string) => void
  openKnowledge: (target: LearningTarget) => void
  openKnowledgeTree: () => void
  goBack: () => void
  goForward: () => void
  returnToCode: () => void
  setReading: (reading: ReadingContext | null) => void
  saveScroll: (key: string, position: number) => void
  resetProject: () => void
}
