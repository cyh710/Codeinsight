/**
 * 项目 store：项目列表、当前项目（持久化到 localStorage `ci.projectId`，
 * 契约 §0.5）、文件与符号（左栏树的数据源）。
 */
import { createStore } from 'zustand'
import { api } from '../api/dataSource'
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
    // 文件树要一次拉全（契约：裸数组）；符号全量 790 个也拉全，
    // 左栏的"点文件展开符号"需要离线过滤，不值得为此再发请求。
    const [files, symbolsRes] = await Promise.all([
      api.getProjectFiles(projectId),
      api.listProjectSymbols(projectId, { limit: 500 }),
    ])
    const symbols: SymbolListItem[] = [...symbolsRes.items]
    set({ files, symbols, loading: false })
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    set({ loading: false, error: msg })
  }
}

export const projectStore = createStore<ProjectStore>((set, get) => ({
  projects: [] as ProjectSummary[],
  currentProjectId: null,
  files: [] as FileEntry[],
  symbols: [] as SymbolListItem[],
  loading: false,
  error: '',

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
}))
