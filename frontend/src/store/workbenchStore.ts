/**
 * 工作台 store：左栏选中态 + 右栏形态。
 *
 * 右栏的三种形态（已对齐 C-Q1/C-Q3）：证据面板是默认态；点符号 →
 * 符号详情**替换右栏**；点概念 → 概念卡**替换右栏**（不弹层——弹层
 * 会挡住证据）。返回证据面板是显式动作，不是自动回切。
 */
import { createStore } from 'zustand'
import type { WorkbenchStore } from './types'

export const workbenchStore = createStore<WorkbenchStore>((set) => ({
  selectedPath: null,
  expandedDirs: {},
  expandedFiles: {},
  treeFilter: '',
  rightPanel: { mode: 'evidence' },

  selectFile: (path: string) => set({ selectedPath: path }),

  selectSymbol: (qualname: string, path: string) =>
    set({ selectedPath: path, rightPanel: { mode: 'symbol', qualname } }),

  openConcept: (conceptId: string) => set({ rightPanel: { mode: 'concept', conceptId } }),

  backToEvidence: () => set({ rightPanel: { mode: 'evidence' } }),

  toggleDir: (path: string) =>
    set((s) => ({ expandedDirs: { ...s.expandedDirs, [path]: !s.expandedDirs[path] } })),

  toggleFile: (path: string) =>
    set((s) => ({ expandedFiles: { ...s.expandedFiles, [path]: !s.expandedFiles[path] } })),

  setTreeFilter: (q: string) => set({ treeFilter: q }),
}))
