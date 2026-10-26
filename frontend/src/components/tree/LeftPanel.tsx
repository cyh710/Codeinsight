/**
 * 左栏：项目切换器（顶部，C-Q6 已对齐）+ 搜索框 + 文件/符号树。
 *
 * 两级联动（C-Q1 已对齐）：文件是心智入口；点开文件展开它的符号；
 * 顶部搜索同时过滤文件路径与符号名。
 */
import { useEffect, useMemo, useState } from 'react'
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
  MessageSquare,
  Files,
} from 'lucide-react'
import { api } from '../../api/dataSource'
import { projectStore } from '../../store/projectStore'
import { workbenchStore } from '../../store/workbenchStore'
import Select from '../common/Select'
import ConversationList from '../chat/ConversationList'
import { layoutStore } from '../../store/layoutStore'
import ImportProjectDialog from './ImportProjectDialog'
import RelocateProjectDialog from './RelocateProjectDialog'
import ProjectActions from './ProjectActions'
import { projectStatusView } from './projectStatusView'
import type { ProjectSummary, SymbolListItem } from '../../api/types'
import {
  buildFileTree,
  filterTree,
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

function StatusLine({ onRelocate }: { onRelocate: () => void }) {
  const detail = useStore(projectStore, (s) => s.currentDetail)
  if (!detail) return null
  if (detail.status === 'indexing') return null
  if (detail.source_available === false || detail.status === 'failed') return <div role="status" className="mt-2 text-xs leading-5 text-amber-700">
    <p>{detail.index_error || (detail.source_available === false ? '找不到源码目录，历史和教材仍可阅读。' : '索引失败，请重新选择目录后重试。')}</p>
    <p className="truncate text-slate-500" title={detail.root_path}>{detail.root_path}</p>
    <button className="mt-1 rounded text-accent hover:underline" onClick={onRelocate}>重新定位</button>
  </div>
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

function NodeRow({ node, depth, symbolsByPath, searching }: {
  node: TreeNode
  depth: number
  symbolsByPath: Map<string, SymbolListItem[]>
  /** 搜索态：数字显示命中符号数，不是文件总符号数。 */
  searching: boolean
}) {
  const workbench = useStore(workbenchStore)
  const filtering = workbench.treeFilter.trim().length > 0
  const pad = { paddingLeft: `${8 + depth * 14}px` }

  // hook 必须无条件调用：文件 / 目录 / folded 三种分支共用同一组。
  const isFile = node.kind === 'file'
  const file = isFile ? node.file! : null
  // 搜索态自动展开：命中的符号藏在折叠的目录里等于没搜到。
  const isOpen = isFile
    ? workbench.expandedFiles[node.path] || searching
    : false
  // 有符号才给展开箭头——用文件自带的 symbol_count 判断，
  // 不用"已加载的符号数"（没展开时那个永远是 0）。
  const hasSymbols = file ? file.symbol_count > 0 : false
  const loadingSymbols = useStore(projectStore, (s) => s.loadingPaths.has(node.path))

  // 展开时按需拉这个文件的符号（契约 §0.4 的 limit 上限 500，
  // 一次性拉全量拿不到 6543 个符号）。
  // 搜索态不拉：命中符号已经在搜索结果里了。
  useEffect(() => {
    if (!isOpen || !hasSymbols || searching) return
    void projectStore.getState().loadSymbolsForPath(node.path)
  }, [isOpen, hasSymbols, searching, node.path])

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

  if (isFile) {
    const f = file!
    const deem = isDeemphasizedRole(f.role)
    const symbols = symbolsByPath.get(node.path) ?? []
    // 搜索态：显示的是**命中几个符号**，不是文件一共几个——
    // 路径命中的文件（比如 "prepare_chat_stream" 也出现在 pet.py 的
    // 路径里）会显示 100，但实际只命中 1 个符号。
    const count = searching ? symbols.length : f.symbol_count
    return (
      <div>
        <div className="flex items-center" style={pad}>
          {hasSymbols ? <button type="button" aria-label={`${isOpen ? '收起' : '展开'} ${node.name} 的函数`} aria-expanded={isOpen} onClick={() => workbench.toggleFile(node.path)} className="shrink-0 rounded p-1 text-slate-400 hover:bg-accent-soft">{isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}</button> : <span className="w-5 shrink-0" />}
          <button
            type="button"
            onClick={() => workbench.selectFile(node.path)}
            className="flex min-w-0 flex-1 items-center gap-1 rounded px-1.5 py-1 text-left text-xs transition-colors hover:bg-accent-soft/50"
            title={node.path}
            data-testid="tree-file"
          >
            {f.language === 'python' ? (
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
            <RoleBadge role={f.role} />
            {loadingSymbols ? (
              <Loader2 size={11} strokeWidth={2} className="ml-auto shrink-0 animate-spin text-slate-300" />
            ) : searching ? (
              count > 0 && (
                <span className="ml-auto shrink-0 text-[10px] text-slate-300">{count}</span>
              )
            ) : (
              hasSymbols && (
                <span className="ml-auto shrink-0 text-[10px] text-slate-300">{f.symbol_count}</span>
              )
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
          <NodeRow
            key={child.path}
            node={child}
            depth={depth + 1}
            symbolsByPath={symbolsByPath}
            searching={searching}
          />
        ))}
    </div>
  )
}

export default function LeftPanel() {
  const sidebar = useStore(layoutStore, s => s.sidebar)
  const projectsState = useStore(projectStore)
  const treeFilter = useStore(workbenchStore, (s) => s.treeFilter)
  const [importOpen, setImportOpen] = useState(false)
  const [relocateProject, setRelocateProject] = useState<ProjectSummary | null>(null)

  // 已按文件加载的符号（展开时按需拉）。分组不用再算——store 已是 path → 符号。
  const symbolsByPath = projectsState.symbolsByPath
  // buildFileTree 同理：688 个文件每次 render 重算太浪费，以引用为键缓存。
  const files = projectsState.files

  // 符号名搜索走后端：契约 §0.4 的 limit 上限 500，前端手上永远只有
  // 已展开的那几个文件的符号，拿它过滤等于搜不到别的文件里的符号。
  // 结果按 path 归组，让命中符号所在的文件在树里露出来。
  const [searchRetry, setSearchRetry] = useState(0)
  const [symbolHits, setSymbolHits] = useState<{ projectId: number | null; query: string; byPath: Map<string, SymbolListItem[]>; error?: string }>({
    projectId: null,
    query: '',
    byPath: new Map(),
  })
  const q = treeFilter.trim()
  useEffect(() => {
    const projectId = projectsState.currentProjectId
    if (q.length < 2 || projectId === null) return
    let alive = true
    const timer = window.setTimeout(() => {
      api
        .listProjectSymbols(projectId, { q, limit: 200 })
        .then((res) => {
          if (!alive) return
          const byPath = new Map<string, SymbolListItem[]>()
          for (const s of res.items) {
            const list = byPath.get(s.path) ?? []
            list.push(s)
            byPath.set(s.path, list)
          }
          setSymbolHits({ projectId, query: q, byPath })
        })
        .catch(error => alive && setSymbolHits({ projectId, query: q, byPath: new Map(), error: String(error) }))
    }, 220)
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
  }, [q, projectsState.currentProjectId, searchRetry])

  // 路径过滤立刻生效（1 个字符就能筛路径）；符号搜索要 ≥2 字符才发请求，
  // 所以"符号结果是否已到"要单独判断，不能拿 query 字符串当同一个东西用。
  const currentHits = symbolHits.projectId === projectsState.currentProjectId && symbolHits.query === q
  const symbolQuery = currentHits ? q : ''
  const hitPaths = useMemo(
    () => new Set(currentHits ? symbolHits.byPath.keys() : []),
    [symbolHits.byPath, currentHits],
  )
  const treeWithSymbols = useMemo(
    () => filterTree(buildFileTree(files), treeFilter, hitPaths),
    [files, treeFilter, hitPaths],
  )

  // 搜索态下，命中的符号直接列在文件下面；不在搜索态就用已加载的。
  const displaySymbols = useMemo(() => {
    if (!symbolQuery) return symbolsByPath
    const merged = new Map(symbolsByPath)
    for (const [path, list] of symbolHits.byPath) merged.set(path, list)
    return merged
  }, [symbolQuery, symbolsByPath, symbolHits.byPath])

  // 搜索态：搜索框里有字就是搜索态（哪怕只 1 个字符、符号结果还没到）。
  const searching = treeFilter.trim().length > 0

  // 页脚总数：项目详情里的 symbols 是权威值；详情还没到就用文件树
  // 自带的 symbol_count 之和。**不能用已加载符号的长度**——那是
  // "展开了多少"不是"一共有多少"（契约 §0.4 的 limit 上限 500，
  // 一次性拉不全 6543 个）。
  const totalSymbols =
    projectsState.currentDetail?.symbols ??
    files.reduce((sum, f) => sum + f.symbol_count, 0)

  return (
    <aside className="agent-sidebar flex h-full min-h-0 w-full shrink-0 flex-col bg-bg-elevated" aria-label="项目与对话导航" aria-busy={projectsState.loading || (projectsState.currentProjectId !== null && !projectsState.currentDetail)}>
      {/* 项目切换器：左栏顶部（C-Q6 已对齐）。 */}
      <div className="sidebar-project-header">
        {/* 自绘 Select（通用件）：API 与原生下拉兼容，但走统一的
            listbox 语义与动效——随基建复制的契约测试要求原生下拉
            元素全局退场。 */}
        <div className="sidebar-project-row"><FolderOpen size={20} className="sidebar-project-icon" aria-hidden="true" /><Select
          className="sidebar-project-select"
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
              {p.name}{p.id === projectsState.currentProjectId && projectsState.currentDetail?.status === 'indexing' ? ' · 索引中' : ''}
            </option>
          ))}
        </Select>{projectsState.currentProjectId !== null && projectsState.projects.find(p => p.id === projectsState.currentProjectId) && <ProjectActions
          key={projectsState.currentProjectId} project={projectsState.currentDetail ?? projectsState.projects.find(p => p.id === projectsState.currentProjectId)!}
          onRelocate={() => setRelocateProject(projectsState.currentDetail ?? projectsState.projects.find(p => p.id === projectsState.currentProjectId)!)} />}
          <button type="button" onClick={() => setImportOpen(true)} className="wb-icon-button sidebar-import" title="导入项目并建索引" aria-label="导入项目并建索引"><FolderInput size={17} strokeWidth={1.7} /></button>
        </div>
        <StatusLine onRelocate={() => { if (projectsState.currentDetail) setRelocateProject(projectsState.currentDetail) }} />
      </div>
      <ImportProjectDialog open={importOpen} onClose={() => setImportOpen(false)} />

      <nav aria-label="左栏内容" className="sidebar-view-tabs">
        <button type="button" aria-pressed={sidebar === 'conversations'} onClick={() => layoutStore.getState().setSidebar('conversations')}><MessageSquare size={15} aria-hidden="true" />对话</button>
        <button type="button" aria-pressed={sidebar === 'files'} onClick={() => layoutStore.getState().setSidebar('files')}><Files size={15} aria-hidden="true" />文件</button>
      </nav>
      {sidebar === 'conversations' ? <ConversationList /> : <>

      {/* 搜索：同时作用于文件路径与符号名。 */}
      <div className="sidebar-file-search">
        <div className="sidebar-search-field">
          <Search size={13} strokeWidth={1.8} className="shrink-0 text-slate-400" />
          <input
            className="min-w-0 flex-1 bg-transparent text-xs text-slate-700 outline-none placeholder:text-slate-400"
            placeholder="搜索文件或符号…"
            value={treeFilter}
            onChange={(e) => workbenchStore.getState().setTreeFilter(e.target.value)}
          />
        </div>
      </div>

      <div className="sidebar-file-tree min-h-0 flex-1 overflow-y-auto px-1.5 py-2">
        {q.length >= 2 && !currentHits && <p role="status" className="p-2 text-xs text-slate-400">正在查找文件和函数…</p>}
        {currentHits && symbolHits.error && <p role="alert" className="p-2 text-xs text-danger">函数搜索失败：{symbolHits.error} <button onClick={() => setSearchRetry(value => value + 1)}>重试</button></p>}
        {projectsState.loading && <p className="px-2 py-4 text-xs text-slate-400">加载索引中…</p>}
        {projectsState.error && (
          <p className="px-2 py-4 text-xs text-danger" role="alert">
            {projectsState.error}
          </p>
        )}
        {projectsState.currentDetail?.status === 'indexing' && !searching && treeWithSymbols.length === 0 && <div className="px-3 py-3" aria-label="正在准备项目文件" aria-busy="true">
          <p className="mb-4 text-xs text-slate-500">正在准备项目文件，完成后自动显示。</p>
          <div className="space-y-3" aria-hidden="true">{[70, 92, 58, 82, 65, 88].map((width, index) => <div key={index} className="h-2.5 rounded bg-slate-200/70 motion-safe:animate-pulse" style={{ width: `${width}%`, marginLeft: index % 3 === 0 ? 0 : 12 }} />)}</div>
        </div>}
        {!projectsState.loading && !projectsState.error && projectsState.currentDetail?.status !== 'indexing' && treeWithSymbols.length === 0 && (
          <p className="px-2 py-4 text-xs text-slate-400">没有匹配的文件。</p>
        )}
        {treeWithSymbols.map((node) => (
          <NodeRow
            key={node.path}
            node={node}
            depth={0}
            symbolsByPath={displaySymbols}
            searching={searching}
          />
        ))}
      </div>

      <div className="sidebar-footer">
        {projectsState.currentDetail?.status === 'indexing' && !projectsState.files.length ? '索引完成后显示文件与符号数量' : `${projectsState.files.length} 文件 · ${totalSymbols} 符号`}
      </div>
      </>}
      {!projectsState.projects.length && <button className="sidebar-empty-import" onClick={() => setImportOpen(true)}><FolderInput size={17} />导入第一个项目</button>}
      {relocateProject && <RelocateProjectDialog key={relocateProject.id} project={relocateProject} onClose={() => setRelocateProject(null)} />}
    </aside>
  )
}
