/**
 * 左栏：项目切换器（顶部，C-Q6 已对齐）+ 搜索框 + 文件/符号树。
 *
 * 两级联动（C-Q1 已对齐）：文件是心智入口；点开文件展开它的符号；
 * 顶部搜索同时过滤文件路径与符号名。
 */
import { useMemo, useState } from 'react'
import { useStore } from 'zustand'
import {
  ChevronDown,
  ChevronRight,
  FileCode2,
  FileText,
  Folder,
  FolderInput,
  FolderOpen,
  Loader2,
  Package,
  Search,
} from 'lucide-react'
import { projectStore } from '../../store/projectStore'
import { workbenchStore } from '../../store/workbenchStore'
import Select from '../common/Select'
import ImportProjectDialog from './ImportProjectDialog'
import { projectStatusView } from './projectStatusView'
import type { SymbolListItem } from '../../api/types'
import {
  buildFileTree,
  filterTree,
  groupSymbolsByPath,
  isDeemphasizedRole,
  symbolKindLabel,
  type TreeNode,
} from './fileTreeModel'

function RoleBadge({ role }: { role: string }) {
  if (role === 'source') return null
  const cls: Record<string, string> = {
    test: 'bg-success/10 text-success',
    config: 'bg-warning/10 text-warning',
    doc: 'bg-accent-soft text-accent',
    vendored: 'bg-slate-200/70 text-slate-500',
    generated: 'bg-slate-200/70 text-slate-500',
  }
  return (
    <span
      className={`ml-1.5 rounded px-1 py-px text-[10px] leading-none ${cls[role] ?? 'bg-slate-100 text-slate-400'}`}
    >
      {role}
    </span>
  )
}

function SymbolRow({ path, symbol, onPick }: {
  path: string
  symbol: SymbolListItem
  onPick: (qualname: string, path: string) => void
}) {
  return (
    <button
      type="button"
      onClick={() => onPick(symbol.qualname, path)}
      className="flex w-full items-center gap-1.5 rounded px-2 py-1 text-left text-xs text-slate-600 transition-colors hover:bg-accent-soft/60 hover:text-accent"
      title={symbol.qualname}
    >
      <span className="w-9 shrink-0 text-[10px] font-medium uppercase text-slate-400">
        {symbolKindLabel(symbol.kind)}
      </span>
      <span className="truncate font-mono">{symbol.name}</span>
    </button>
  )
}

function StatusLine() {
  const detail = useStore(projectStore, (s) => s.currentDetail)
  if (!detail) return null
  const view = projectStatusView(detail.status)
  if (view.tone === 'none') return null
  const cls =
    view.tone === 'danger'
      ? 'text-danger'
      : view.tone === 'warning'
        ? 'text-warning'
        : 'text-accent'
  return (
    <p className={`mt-1.5 flex items-center gap-1 text-[10.5px] ${cls}`} title={view.title} role="status">
      {view.tone === 'info' ? (
        <Loader2 size={11} strokeWidth={1.8} className="shrink-0 animate-spin" />
      ) : null}
      {view.label}
      {view.tone === 'warning' && <span className="text-slate-400">·重新导入可刷新</span>}
    </p>
  )
}

function NodeRow({ node, depth, symbolsByPath }: {
  node: TreeNode
  depth: number
  symbolsByPath: Map<string, SymbolListItem[]>
}) {
  const workbench = useStore(workbenchStore)
  const filtering = workbench.treeFilter.trim().length > 0
  const pad = { paddingLeft: `${8 + depth * 14}px` }

  if (node.kind === 'folded') {
    return (
      <div
        className="flex items-center gap-1.5 rounded px-2 py-1 text-xs text-slate-400"
        style={pad}
        title={`${node.path}/ 是第三方或生成代码，默认折叠（ADR 0015 第二档）`}
      >
        <Package size={13} strokeWidth={1.6} className="shrink-0" />
        <span className="truncate">{node.name}</span>
        <span className="ml-auto shrink-0 text-[10px]">{node.foldedCount} 文件</span>
      </div>
    )
  }

  if (node.kind === 'file') {
    const file = node.file!
    const deem = isDeemphasizedRole(file.role)
    const isOpen = workbench.expandedFiles[node.path] || false
    const symbols = symbolsByPath.get(node.path) ?? []
    return (
      <div>
        <div className="flex items-center" style={pad}>
          <button
            type="button"
            onClick={() => workbench.selectFile(node.path)}
            className="flex min-w-0 flex-1 items-center gap-1 rounded px-1.5 py-1 text-left text-xs transition-colors hover:bg-accent-soft/50"
            title={node.path}
            data-testid="tree-file"
          >
            {symbols.length > 0 ? (
              <span
                role="button"
                tabIndex={-1}
                onClick={(e) => {
                  e.stopPropagation()
                  workbench.toggleFile(node.path)
                }}
                className="shrink-0"
              >
                {isOpen ? (
                  <ChevronDown size={12} strokeWidth={1.8} className="text-slate-400" />
                ) : (
                  <ChevronRight size={12} strokeWidth={1.8} className="text-slate-400" />
                )}
              </span>
            ) : (
              <span className="w-3 shrink-0" />
            )}
            {file.language === 'python' ? (
              <FileCode2
                size={13}
                strokeWidth={1.6}
                className={`shrink-0 ${deem ? 'text-slate-300' : 'text-accent/70'}`}
              />
            ) : (
              <FileText
                size={13}
                strokeWidth={1.6}
                className={`shrink-0 ${deem ? 'text-slate-300' : 'text-slate-400'}`}
              />
            )}
            <span
              className={`truncate font-mono ${
                deem
                  ? 'text-slate-400'
                  : workbench.selectedPath === node.path
                    ? 'font-medium text-accent'
                    : 'text-slate-700'
              }`}
            >
              {node.name}
            </span>
            <RoleBadge role={file.role} />
            {symbols.length > 0 && (
              <span className="ml-auto shrink-0 text-[10px] text-slate-300">{symbols.length}</span>
            )}
          </button>
        </div>
        {isOpen && (
          <div className="pb-1">
            {symbols.map((s) => (
              <SymbolRow
                key={`${s.qualname}:${s.lineno}`}
                path={node.path}
                symbol={s}
                onPick={workbench.selectSymbol}
              />
            ))}
          </div>
        )}
      </div>
    )
  }

  // 目录
  const open = filtering || workbench.expandedDirs[node.path]
  return (
    <div>
      <button
        type="button"
        onClick={() => workbench.toggleDir(node.path)}
        className="flex w-full items-center gap-1.5 rounded px-2 py-1 text-left text-xs font-medium text-slate-600 transition-colors hover:bg-accent-soft/50"
        style={pad}
      >
        {open ? (
          <ChevronDown size={12} strokeWidth={1.8} className="shrink-0 text-slate-400" />
        ) : (
          <ChevronRight size={12} strokeWidth={1.8} className="shrink-0 text-slate-400" />
        )}
        {open ? (
          <FolderOpen size={13} strokeWidth={1.6} className="shrink-0 text-accent/70" />
        ) : (
          <Folder size={13} strokeWidth={1.6} className="shrink-0 text-accent/70" />
        )}
        <span className="truncate">{node.name}</span>
      </button>
      {open &&
        (node.children ?? []).map((child) => (
          <NodeRow key={child.path} node={child} depth={depth + 1} symbolsByPath={symbolsByPath} />
        ))}
    </div>
  )
}

export default function LeftPanel() {
  const projectsState = useStore(projectStore)
  const treeFilter = useStore(workbenchStore, (s) => s.treeFilter)
  const [importOpen, setImportOpen] = useState(false)

  // 688 文件 × 790 符号的分组与建树都以引用为键用 useMemo 缓存，
  // projectStore 只在换项目时换引用，平时 render 零重算。
  const symbolsByPath = useMemo(() => groupSymbolsByPath(projectsState.symbols), [projectsState.symbols])
  // buildFileTree 同理：688 个文件每次 render 重算太浪费，以引用为键缓存。
  const files = projectsState.files
  const tree = useMemo(
    () => filterTree(buildFileTree(files), treeFilter),
    [files, treeFilter],
  )

  return (
    <aside className="flex h-full min-h-0 w-72 shrink-0 flex-col border-r border-slate-200/80 bg-bg-elevated">
      {/* 项目切换器：左栏顶部（C-Q6 已对齐）。 */}
      <div className="border-b border-slate-200/70 px-3 py-2.5">
        <div className="flex items-center justify-between">
          <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            项目
          </label>
          <button
            type="button"
            onClick={() => setImportOpen(true)}
            className="flex h-5.5 w-5.5 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-accent-soft hover:text-accent"
            title="导入项目并建索引"
            aria-label="导入项目并建索引"
          >
            <FolderInput size={13} strokeWidth={1.7} />
          </button>
        </div>
        {/* 自绘 Select（通用件）：API 与原生下拉兼容，但走统一的
            listbox 语义与动效——随基建复制的契约测试要求原生下拉
            元素全局退场。 */}
        <Select
          className="mt-1"
          label="选择项目"
          value={projectsState.currentProjectId === null ? '' : String(projectsState.currentProjectId)}
          onChange={(e) => {
            const id = Number(e.target.value)
            if (Number.isInteger(id) && id > 0) void projectsState.selectProject(id)
          }}
        >
          {projectsState.projects.length === 0 && <option value="">（无项目）</option>}
          {projectsState.projects.map((p) => (
            <option key={p.id} value={String(p.id)}>
              {p.name}（{p.symbols} 符号）
            </option>
          ))}
        </Select>
        <StatusLine />
      </div>
      <ImportProjectDialog open={importOpen} onClose={() => setImportOpen(false)} />

      {/* 搜索：同时作用于文件路径与符号名。 */}
      <div className="border-b border-slate-200/70 px-3 py-2">
        <div className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2 py-1.5 focus-within:border-accent">
          <Search size={13} strokeWidth={1.8} className="shrink-0 text-slate-400" />
          <input
            className="min-w-0 flex-1 bg-transparent text-xs text-slate-700 outline-none placeholder:text-slate-400"
            placeholder="搜索文件或符号…"
            value={treeFilter}
            onChange={(e) => workbenchStore.getState().setTreeFilter(e.target.value)}
          />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 py-2">
        {projectsState.loading && <p className="px-2 py-4 text-xs text-slate-400">加载索引中…</p>}
        {projectsState.error && (
          <p className="px-2 py-4 text-xs text-danger" role="alert">
            {projectsState.error}
          </p>
        )}
        {!projectsState.loading && !projectsState.error && tree.length === 0 && (
          <p className="px-2 py-4 text-xs text-slate-400">没有匹配的文件。</p>
        )}
        {tree.map((node) => (
          <NodeRow key={node.path} node={node} depth={0} symbolsByPath={symbolsByPath} />
        ))}
      </div>

      <div className="border-t border-slate-200/70 px-3 py-1.5 text-[10px] text-slate-400">
        {projectsState.files.length} 文件 · {projectsState.symbols.length} 符号
      </div>
    </aside>
  )
}
