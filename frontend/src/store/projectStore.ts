/**
 * 项目 store：项目列表、当前项目（持久化到 localStorage `ci.projectId`，
 * 契约 §0.5）、文件与符号（左栏树的数据源）、导入项目的轮询状态。
 */
import { createStore } from 'zustand'
import { api } from '../api/dataSource'
import { waitForIndexing } from '../api/importFlow'
import { ApiError } from '../api/client'
import type { FileEntry, ProjectDetail, ProjectSummary, SymbolListItem } from '../api/types'
import { chatStore } from './chatStore'
import type { IndexActivity, ProjectStore } from './types'
import { workbenchStore } from './workbenchStore'
import { hotState } from './hotState'
import { removeProjectLocal } from './persistence'

const STORAGE_KEY = 'ci.projectId'
const indexMonitors = new Map<number, AbortController>()

function errorText(error: unknown): string {
  return error instanceof ApiError ? `${error.title}。${error.hint}` : error instanceof Error ? error.message : String(error)
}

function updateActivity(id: number, patch: Partial<IndexActivity>) {
  projectStore.setState(state => {
    const previous = state.indexActivities[id]
    if (!previous) return {}
    return { indexActivities: { ...state.indexActivities, [id]: { ...previous, ...patch } } }
  })
}

function observeIndex(detail: ProjectDetail) {
  const state = projectStore.getState()
  if (!state.indexActivities[detail.id] && ['indexing', 'failed'].includes(detail.status)) {
    projectStore.setState({ indexActivities: { ...state.indexActivities, [detail.id]: {
      projectId: detail.id, name: detail.name, phase: detail.status === 'failed' ? 'failed' : 'indexing',
      observedAt: Date.now(), detail, message: detail.index_error || undefined,
    } } })
  }
  if (detail.status === 'indexing') monitorIndex(detail.id)
}

function monitorIndex(id: number) {
  if (indexMonitors.has(id) || !projectStore.getState().indexActivities[id]) return
  const token = new AbortController()
  indexMonitors.set(id, token)
  updateActivity(id, { phase: 'indexing', message: undefined })
  void (async () => {
    try {
      const detail = await waitForIndexing(projectId => api.getProject(projectId), id, {
        signal: token.signal,
        onError: error => {
          if (indexMonitors.get(id) !== token) return
          updateActivity(id, { phase: 'unavailable', message: `${errorText(error)} 正在自动重试检查。` })
        },
        onTick: current => {
          if (indexMonitors.get(id) !== token) return
          updateActivity(id, { detail: current, name: current.name,
            phase: current.status === 'indexing' ? 'indexing' : current.status === 'failed' ? 'failed' : 'syncing', message: undefined })
          if (projectStore.getState().currentProjectId === id) projectStore.setState({ currentDetail: current, loading: false })
        },
      })
      if (indexMonitors.get(id) !== token) return
      if (detail.status === 'indexing') {
        updateActivity(id, { phase: 'paused', message: '索引仍未完成，自动检查已暂停。可继续检查，不会重复建立索引。' })
      } else if (detail.status === 'failed') {
        updateActivity(id, { phase: 'failed', message: detail.index_error || '本次索引未完成，请检查项目目录和提交版本。' })
      } else {
        updateActivity(id, { phase: 'syncing' })
        if (projectStore.getState().currentProjectId === id) {
          const loaded = await loadProjectData(partial => projectStore.setState(partial), id)
          if (!loaded && projectStore.getState().currentProjectId === id) throw new Error('索引已建立，文件列表暂未加载成功。请重新检查。')
        }
        projectStore.setState(state => ({ projects: state.projects.map(project => project.id === id ? { ...project, ...detail } : project) }))
        updateActivity(id, { phase: 'ready', detail, message: detail.status === 'stale' ? '索引已建立，但仓库又有新提交；当前结果仍对应已索引版本。' : undefined })
      }
    } catch (error) {
      if (indexMonitors.get(id) !== token || token.signal.aborted) return
      updateActivity(id, { phase: 'unavailable', message: errorText(error) })
    } finally {
      if (indexMonitors.get(id) === token) indexMonitors.delete(id)
    }
  })()
}

function loadStoredProjectId(): number | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const id = raw ? Number(raw) : NaN
    return Number.isInteger(id) && id > 0 ? id : null
  } catch {
    return null
  }
}

function storeProjectId(id: number | null) {
  try {
    if (id === null) localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, String(id))
  } catch {
    // 隐私模式等场景 localStorage 不可用：只是记不住选择，不影响功能。
  }
}

async function loadProjectData(
  set: (partial: Partial<ProjectStore>) => void,
  projectId: number,
): Promise<boolean> {
  set({ loading: true, error: '' })
  try {
    // 文件树一次拉全（契约：裸数组）。每个文件自带 symbol_count，
    // 页脚总数与每文件的符号数都从这里来——不需要额外请求。
    //
    // 符号**不**在这里一次性拉：契约 §0.4 把 limit 上限压在 500，
    // 织忆这种 6543 符号的项目一次拉不全（只覆盖前 31 个文件），
    // 剩下的文件展开后是空的。改成展开文件时按 path 拉（loadSymbolsForPath）。
    const [detail, files] = await Promise.all([
      api.getProject(projectId),
      api.getProjectFiles(projectId),
    ])
    // 竞态防护：切项目时旧请求可能后到，丢弃过期响应，
    // 否则会把上一个项目的数据写进当前项目。
    if (projectStore.getState().currentProjectId !== projectId) return false
    set({
      currentDetail: detail,
      files,
      symbolsByPath: new Map(),
      loadingPaths: new Set(),
      loading: false,
    })
    workbenchStore.getState().setIndexVersion(detail.head_commit)
    observeIndex(detail)
    return true
  } catch (e) {
    if (projectStore.getState().currentProjectId !== projectId) return false
    const msg = e instanceof Error ? e.message : String(e)
    set({ loading: false, error: msg })
    return false
  }
}

export const projectStore = hotState(import.meta.hot, 'projects', () => createStore<ProjectStore>((set, get) => ({
  projects: [] as ProjectSummary[],
  currentProjectId: null,
  currentDetail: null,
  files: [] as FileEntry[],
  symbolsByPath: new Map<string, SymbolListItem[]>(),
  loadingPaths: new Set<string>(),
  loading: false,
  error: '',
  importing: false,
  importError: '',
  indexActivities: {},
  resumeIndexing: id => monitorIndex(id),
  dismissIndexActivity: id => {
    if (indexMonitors.has(id) && ['indexing', 'syncing'].includes(get().indexActivities[id]?.phase)) return
    indexMonitors.get(id)?.abort()
    indexMonitors.delete(id)
    set(state => {
      const next = { ...state.indexActivities }; delete next[id]
      return { indexActivities: next }
    })
  },
  retryIndexing: async id => {
    const request = get().indexActivities[id]?.request
    if (request) {
      await get().importProject(request.root_path, request.name, request.ref)
      if (get().importError) updateActivity(id, { phase: 'failed', message: get().importError })
    }
  },

  init: async () => {
    try {
      const projects = await api.listProjects()
      set({ projects })
      const stored = loadStoredProjectId()
      const preferred = projects.find((p) => p.id === stored)?.id ?? projects[0]?.id ?? null
      if (preferred !== null) {
        set({ currentProjectId: preferred })
        await chatStore.getState().switchProject(preferred)
        storeProjectId(preferred)
        await loadProjectData(set, preferred)
      } else chatStore.setState({ loading: false })
    } catch (e) {
      chatStore.setState({ loading: false })
      set({ error: e instanceof Error ? e.message : String(e) })
    }
  },

  selectProject: async (id: number) => {
    if (get().currentProjectId === id) return
    set({ currentProjectId: id, currentDetail: null, files: [], symbolsByPath: new Map(), loadingPaths: new Set(), loading: true, error: '' })
    storeProjectId(id)
    // 切项目：会话按项目隔离（切回来会恢复该项目的对话），
    // 工作台与中栏视图重置，避免带着上一个项目的上下文继续看。
    await chatStore.getState().switchProject(id)
    await loadProjectData(set, id)
  },

  removeProject: async (id: number) => {
    await api.removeProject(id)
    indexMonitors.get(id)?.abort()
    indexMonitors.delete(id)
    chatStore.getState().forgetProject(id)
    // 确认框卸载前完成缓存清理，避免切换项目后仍残留旧项目的本地记录。
    await removeProjectLocal(id)
    const remaining = get().projects.filter(p => p.id !== id)
    set(s => { const activities = { ...s.indexActivities }; delete activities[id]; return { projects: remaining, indexActivities: activities } })
    if (get().currentProjectId === id) {
      set({ currentProjectId: null, currentDetail: null, files: [], symbolsByPath: new Map(), loadingPaths: new Set(), loading: false, error: '' })
      storeProjectId(null)
      if (remaining.length) await get().selectProject(remaining[0].id)
      else if (typeof history !== 'undefined') history.replaceState(null, '', '/')
    }
  },

  loadSymbolsForPath: async (path: string) => {
    const projectId = get().currentProjectId
    if (projectId === null) return
    if (get().symbolsByPath.has(path)) return
    if (get().loadingPaths.has(path)) return
    set((s) => ({ loadingPaths: new Set(s.loadingPaths).add(path) }))
    try {
      const res = await api.listProjectSymbols(projectId, { path, limit: 500 })
      if (get().currentProjectId !== projectId) return
      set((s) => {
        const next = new Map(s.symbolsByPath)
        next.set(path, res.items)
        return { symbolsByPath: next }
      })
    } catch {
      if (get().currentProjectId !== projectId) return
      // 拉不到就记成空列表：不重试，也不让左栏整块崩掉。
      set((s) => {
        const next = new Map(s.symbolsByPath)
        next.set(path, [])
        return { symbolsByPath: next }
      })
    } finally {
      if (get().currentProjectId === projectId) set((s) => {
        const next = new Set(s.loadingPaths)
        next.delete(path)
        return { loadingPaths: next }
      })
    }
  },

  relocateProject: async (id, rootPath) => {
    if (get().importing) return false
    set({ importing: true, importError: '' })
    try {
      await api.relocateProject(id, { root_path: rootPath })
      set(state => ({ indexActivities: { ...state.indexActivities, [id]: {
        projectId: id, name: state.currentDetail?.id === id ? state.currentDetail.name : state.projects.find(project => project.id === id)?.name || '项目',
        phase: 'indexing', observedAt: Date.now(),
      } } }))
      if (get().currentProjectId === id && get().currentDetail) {
        set({ currentDetail: { ...get().currentDetail!, status: 'indexing', index_error: null } })
      }
      // 只刷新索引数据；同一个项目的对话、草稿、材料及阅读来路保持原身份。
      monitorIndex(id)
      return true
    } catch (error) {
      set({ importError: errorText(error) })
      return false
    } finally {
      set({ importing: false })
    }
  },

  importProject: async (rootPath: string, name?: string, ref?: string) => {
    if (get().importing) return
    set({ importing: true, importError: '' })
    try {
      const created = await api.createProject({
        root_path: rootPath,
        ...(name ? { name } : {}),
        ...(ref ? { ref } : {}),
      })
      const sameProject = get().currentProjectId === created.id
      const previous = sameProject ? get().currentDetail : null
      const pending: ProjectDetail = {
        indexed_at: null, index_epoch: 0, files: 0, symbols: 0, chunks: 0, edges: 0, concepts: 0, concept_instances: 0,
        ...previous, ...created, status: 'indexing', index_error: null,
      }
      const activity: IndexActivity = {
        projectId: created.id, name: created.name, phase: 'indexing', observedAt: Date.now(), detail: pending,
        request: { root_path: rootPath, ...(name ? { name } : {}), ...(ref ? { ref } : {}) },
      }
      set(state => ({
        currentProjectId: created.id, currentDetail: pending, loading: false, error: '',
        ...(sameProject ? {} : { files: [], symbolsByPath: new Map(), loadingPaths: new Set() }),
        projects: state.projects.some(project => project.id === created.id)
          ? state.projects.map(project => project.id === created.id ? { ...project, name: created.name } : project)
          : [...state.projects, pending],
        indexActivities: { ...state.indexActivities, [created.id]: activity },
      }))
      storeProjectId(created.id)
      // 202 代表任务已接受；状态轮询不阻塞提交弹窗，也不能回写后来选择的项目。
      monitorIndex(created.id)
      if (chatStore.getState().projectId !== created.id) void chatStore.getState().switchProject(created.id).catch(error => {
        if (get().currentProjectId === created.id) set({ loading: false, error: `项目状态读取失败：${error instanceof Error ? error.message : String(error)}` })
      })
    } catch (e) {
      const msg = errorText(e)
      set({ importError: msg })
    } finally {
      set({ importing: false })
    }
  },
})))
