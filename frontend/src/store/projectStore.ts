/**
 * 项目 store：项目列表、当前项目（持久化到 localStorage `ci.projectId`，
 * 契约 §0.5）、文件与符号（左栏树的数据源）、导入项目的轮询状态。
 */
import { createStore } from 'zustand'
import { api } from '../api/dataSource'
import { waitForIndexing } from '../api/importFlow'
import type { FileEntry, ProjectSummary, SymbolListItem } from '../api/types'
import type { ProjectStore } from './types'

const STORAGE_KEY = 'ci.projectId'

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
): Promise<void> {
  set({ loading: true, error: '' })
  try {
    // 文件树一次拉全（契约：裸数组）；符号全量拉来做左栏离线过滤，
    // 不值得为"点文件展开符号"再发请求。详情（含状态与计数）同批取。
    const [detail, files, symbolsRes] = await Promise.all([
      api.getProject(projectId),
      api.getProjectFiles(projectId),
      api.listProjectSymbols(projectId, { limit: 500 }),
    ])
    const symbols: SymbolListItem[] = [...symbolsRes.items]
    set({ currentDetail: detail, files, symbols, loading: false })
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    set({ loading: false, error: msg })
  }
}

export const projectStore = createStore<ProjectStore>((set, get) => ({
  projects: [] as ProjectSummary[],
  currentProjectId: null,
  currentDetail: null,
  files: [] as FileEntry[],
  symbols: [] as SymbolListItem[],
  loading: false,
  error: '',
  importing: false,
  importError: '',

  init: async () => {
    try {
      const projects = await api.listProjects()
      set({ projects })
      const stored = loadStoredProjectId()
      const preferred =
        projects.find((p) => p.id === stored)?.id ?? projects[0]?.id ?? null
      if (preferred !== null) {
        set({ currentProjectId: preferred })
        storeProjectId(preferred)
        await loadProjectData(set, preferred)
      }
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) })
    }
  },

  selectProject: async (id: number) => {
    if (get().currentProjectId === id) return
    set({ currentProjectId: id })
    storeProjectId(id)
    await loadProjectData(set, id)
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
      // 列表刷新 + 立即切到新项目（此时 status=indexing，状态行开始转圈）。
      set({ currentProjectId: created.id, currentDetail: null })
      storeProjectId(created.id)
      try {
        set({ projects: await api.listProjects() })
      } catch {
        // 列表刷新失败不阻塞轮询：详情才是权威。
      }
      const detail = await waitForIndexing((id) => api.getProject(id), created.id, {
        // onTick 让状态行（索引中/失败）实时跟着走。
        onTick: (d) => set({ currentDetail: d }),
      })
      set({ currentDetail: detail })
      if (detail.status === 'ready') {
        await loadProjectData(set, created.id)
      }
      // failed/stale：数据保持空/旧，状态行如实呈现，不额外弹错。
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      set({ importError: msg })
    } finally {
      set({ importing: false })
    }
  },
}))
