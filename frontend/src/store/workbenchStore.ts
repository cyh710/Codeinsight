/** 阅读与代码共用右栏历史，阅读目标与旧消息来源版本独立保存。 */
import { createStore } from 'zustand'
import type { ReadingContext } from '../api/types'
import type { WorkbenchStore, RightPanel } from './types'

export function panelKey(panel: RightPanel): string {
  return JSON.stringify(panel)
}

export const workbenchStore = createStore<WorkbenchStore>((set, get) => {
  const navigate = (panel: RightPanel, path = get().selectedPath, reading: ReadingContext | null = null) => {
    const s = get()
    if (panelKey(panel) === panelKey(s.rightPanel)) return
    const history = s.history.slice(0, s.historyIndex + 1)
    history[s.historyIndex] = { panel: s.rightPanel, path: s.selectedPath, reading: s.reading }
    history.push({ panel, path, reading })
    set({ rightPanel: panel, selectedPath: path, reading, history, historyIndex: history.length - 1 })
  }
  const move = (index: number) => {
    const s = get()
    if (index < 0 || index >= s.history.length || index === s.historyIndex) return
    const history = [...s.history]
    history[s.historyIndex] = { panel: s.rightPanel, path: s.selectedPath, reading: s.reading }
    const target = history[index]
    set({ history, historyIndex: index, rightPanel: target.panel, selectedPath: target.path, reading: target.reading })
  }
  return {
    selectedPath: null, expandedDirs: {}, expandedFiles: {}, treeFilter: '',
    rightPanel: { mode: 'evidence' },
    history: [{ panel: { mode: 'evidence' }, path: null, reading: null }],
    historyIndex: 0, reading: null, scrollPositions: {},
    selectFile: (path, lineno = 1) => navigate({ mode: 'file', path, lineno }, path),
    selectSymbol: (qualname, path) => navigate({ mode: 'symbol', qualname }, path, null),
    openConcept: (conceptId) => navigate({ mode: 'concept', conceptId }),
    openKnowledge: (target) => navigate({ mode: 'knowledge', target }),
    openKnowledgeTree: () => navigate({ mode: 'knowledge-tree' }),
    backToEvidence: () => navigate({ mode: 'evidence' }),
    goBack: () => move(get().historyIndex - 1),
    goForward: () => move(get().historyIndex + 1),
    returnToCode: () => {
      const s = get()
      for (let i = s.historyIndex - 1; i >= 0; i--) {
        if (['file', 'symbol'].includes(s.history[i].panel.mode)) { move(i); return }
      }
      if (s.selectedPath) navigate({ mode: 'file', path: s.selectedPath, lineno: 1 })
    },
    setReading: (reading) => set({ reading }),
    saveScroll: (key, position) => set((s) => ({ scrollPositions: { ...s.scrollPositions, [key]: position } })),
    resetProject: () => set({ selectedPath: null, rightPanel: { mode: 'evidence' }, reading: null,
      history: [{ panel: { mode: 'evidence' }, path: null, reading: null }], historyIndex: 0,
      expandedDirs: {}, expandedFiles: {}, scrollPositions: {} }),
    toggleDir: (path) => set((s) => ({ expandedDirs: { ...s.expandedDirs, [path]: !s.expandedDirs[path] } })),
    toggleFile: (path) => set((s) => ({ expandedFiles: { ...s.expandedFiles, [path]: !s.expandedFiles[path] } })),
    setTreeFilter: (q) => set({ treeFilter: q }),
  }
})
