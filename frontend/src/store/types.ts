/**
 * 前端状态类型总集（组织法抄织忆：一个项目一个 `types.ts` 集中放）。
 * 与后端交换的形状一律用 `../api/types.ts` 的冻结类型，这里只放**前端视图状态**。
 */
import type { Citation, Fact, Inference, RetrievalLane, ToolStatus } from '../api/types'

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
  /** 出错时渲染错误卡而不是气泡（code 见契约 §0.3）。 */
  error?: { code: string; title: string; hint: string }
  /** 以下三项只在 assistant 落定后有值（ADR 0007：facts 与 inferences 分栏）。 */
  facts?: Fact[]
  inferences?: Inference[]
  citations?: Citation[]
  abstained?: boolean
  abstentionReason?: string
  /** 本轮的工具时间线（边流边长）。 */
  tools?: ToolTimelineItem[]
  /** 本轮积累的证据（边流边长，右栏实时渲染）。 */
  evidence?: PanelEvidence[]
}

export interface ChatStore {
  messages: ChatMessage[]
  streaming: boolean
  /** 连续追问用；空串 = 新会话。 */
  conversationId: string
  /** 当前流的中止器（"停止"按钮用）。 */
  _abortController: AbortController | null

  sendMessage: (projectId: number, question: string) => Promise<void>
  stopStreaming: () => void
  reset: () => void
}

// ─── 项目 ─────────────────────────────────────────────────────

export interface ProjectStore {
  projects: import('../api/types').ProjectSummary[]
  currentProjectId: number | null
  files: import('../api/types').FileEntry[]
  symbols: import('../api/types').SymbolListItem[]
  loading: boolean
  error: string

  init: () => Promise<void>
  selectProject: (id: number) => Promise<void>
}

// ─── 工作台（当前选中什么、右栏显示什么） ─────────────────────

/** 右栏形态：证据面板，或概念卡（**右栏替换**，已对齐 C-Q3）。 */
export type RightPanel =
  | { mode: 'evidence' }
  | { mode: 'symbol'; qualname: string }
  | { mode: 'concept'; conceptId: string }

export interface WorkbenchStore {
  selectedPath: string | null
  /** 展开的目录（path → true）。 */
  expandedDirs: Record<string, boolean>
  /** 展开了符号列表的文件（path → true）。 */
  expandedFiles: Record<string, boolean>
  treeFilter: string
  rightPanel: RightPanel

  selectFile: (path: string) => void
  selectSymbol: (qualname: string, path: string) => void
  openConcept: (conceptId: string) => void
  backToEvidence: () => void
  toggleDir: (path: string) => void
  toggleFile: (path: string) => void
  setTreeFilter: (q: string) => void
}
