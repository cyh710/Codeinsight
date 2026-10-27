/** 材料页签、位置与提问目标分别保存，自动事件不能抢走用户的阅读。 */
import { createStore } from 'zustand'
import type { ReadingContext } from '../api/types'
import type { WorkbenchStore, RightPanel } from './types'
import { layoutStore } from './layoutStore'
import { readLocal, writeLocal } from './persistence'
import { viewStore } from './viewStore'
import { hotState } from './hotState'

export function panelKey(panel: RightPanel): string { return JSON.stringify(panel) }
export function materialKey(panel: RightPanel): string {
  if (panel.mode === 'exploration') return `exploration:${panel.projectId}:${panel.conversationId}:${panel.requestId}:${panel.target.topic_id}:${panel.target.section_id}:${panel.target.version}`
  if (panel.mode === 'knowledge') return `knowledge:${panel.target.topic_id}:${panel.target.version}`
  if (panel.mode === 'file') return `file:${panel.path}:${panel.version ?? ''}${panel.indexEpoch === undefined ? '' : `:epoch:${panel.indexEpoch}`}${panel.sourceKind === 'workspace' ? `:workspace:${panel.contentSha ?? ''}` : ''}`
  if (panel.mode === 'symbol') return `symbol:${panel.qualname}:${panel.version ?? ''}`
  if (panel.mode === 'concept') return `concept:${panel.conceptId}`
  return panelKey(panel)
}
export function materialTitle(panel: RightPanel): string {
  if (panel.mode === 'exploration') return `理解：${panel.target.section_title ?? panel.target.title}`
  if (panel.mode === 'knowledge') return panel.target.title
  if (panel.mode === 'file') return panel.path.split('/').at(-1) || panel.path
  if (panel.mode === 'symbol') return panel.qualname.split('.').at(-1) || panel.qualname
  if (panel.mode === 'concept') return panel.conceptId
  return panel.mode === 'knowledge-tree' ? '教材目录' : '回答来源'
}
const empty = () => ({
  selectedPath: null, expandedDirs: {}, expandedFiles: {}, treeFilter: '',
  rightPanel: { mode: 'evidence' } as RightPanel,
  history: [{ panel: { mode: 'evidence' } as RightPanel, path: null, reading: null }],
  historyIndex: 0, reading: null, scrollPositions: {}, directoryQuery: '',
  tabs: [{ id: materialKey({ mode: 'evidence' }), panel: { mode: 'evidence' } as RightPanel, title: '回答来源' }],
  activeTab: materialKey({ mode: 'evidence' }), closedTabs: [], pinned: false,
  followEvidence: false, newEvidence: false, readingMode: 'follow' as const,
  indexVersion: null, chatScroll: null, codePositions: {},
})
const workspace = hotState(import.meta.hot, 'workspace', () => {
  const workbenchStore = createStore<WorkbenchStore>((set, get) => {
    const display = (panel: RightPanel) => {
      const id = materialKey(panel)
      const tabs = [...get().tabs]
      const index = tabs.findIndex(t => t.id === id)
      const tab = { id, panel, title: materialTitle(panel) }
      if (index >= 0) tabs[index] = tab; else tabs.push(tab)
      set({ tabs, activeTab: id, rightPanel: panel })
    }
    const navigate = (panel: RightPanel, path = get().selectedPath, reading: ReadingContext | null = null) => {
      layoutStore.getState().showRight()
      const s = get()
      if (panelKey(panel) === panelKey(s.rightPanel)) return
      const history = s.history.slice(0, s.historyIndex + 1)
      history[s.historyIndex] = { panel: s.rightPanel, path: s.selectedPath, reading: s.reading }
      history.push({ panel, path, reading })
      set({ selectedPath: path, reading: s.readingMode === 'follow' ? reading : s.reading, history, historyIndex: history.length - 1 })
      display(panel)
    }
    const move = (index: number) => {
      const s = get()
      if (index < 0 || index >= s.history.length || index === s.historyIndex) return
      const history = [...s.history]
      history[s.historyIndex] = { panel: s.rightPanel, path: s.selectedPath, reading: s.reading }
      const target = history[index]
      set({ history, historyIndex: index, selectedPath: target.path,
        reading: s.readingMode === 'follow' ? target.reading : s.reading })
      display(target.panel)
      layoutStore.getState().showRight()
    }
    return {
      ...empty(),
      setDirectoryQuery: directoryQuery => set({ directoryQuery }),
      setIndexVersion: indexVersion => set({ indexVersion }),
      bindFileVersion: (path, lineno, version, indexEpoch, sourceKind, contentSha) => {
        const s = get(), panel = s.rightPanel
        if (panel.mode !== 'file' || panel.path !== path || panel.lineno !== lineno || panel.contentSha || panel.indexEpoch !== undefined || (indexEpoch === undefined && sourceKind !== 'workspace')) return
        const resolved: RightPanel = { ...panel, ...(version ? { version } : {}), ...(indexEpoch === undefined ? {} : { indexEpoch }), ...(sourceKind ? { sourceKind } : {}), ...(contentSha ? { contentSha } : {}) }
        const oldId = materialKey(panel), id = materialKey(resolved)
        set({ rightPanel: resolved, activeTab: id,
          tabs: s.tabs.filter(t => t.id !== id || t.id === oldId).map(t => t.id === oldId ? { ...t, id, panel: resolved } : t),
          history: s.history.map(h => panelKey(h.panel) === panelKey(panel) ? { ...h, panel: resolved } : h),
          scrollPositions: { ...s.scrollPositions, [panelKey(resolved)]: s.scrollPositions[panelKey(panel)] ?? 0 } })
      },
      setChatScroll: chatScroll => set({ chatScroll }),
      saveCodePosition: (key, value) => set(s => ({ codePositions: { ...s.codePositions, [key]: value } })),
      selectFile: (path, lineno = 1, version, indexEpoch, sourceKind, contentSha) => navigate({ mode: 'file', path, lineno, ...(version ? { version } : {}), ...(indexEpoch === undefined ? {} : { indexEpoch }), ...(sourceKind ? { sourceKind } : {}), ...(contentSha ? { contentSha } : {}) }, path),
      selectSymbol: (qualname, path, lineno, version = get().indexVersion) => navigate({ mode: 'symbol', qualname, lineno, ...(version ? { version } : {}) }, path),
      openConcept: conceptId => navigate({ mode: 'concept', conceptId }),
      openMaterial: panel => navigate(panel, panel.mode === 'file' ? panel.path : get().selectedPath),
      openKnowledge: target => navigate({ mode: 'knowledge', target }),
      openKnowledgeTree: () => navigate({ mode: 'knowledge-tree' }),
      backToEvidence: () => navigate({ mode: 'evidence' }),
      openEvidence: messageId => { set({ newEvidence: false }); navigate({ mode: 'evidence', ...(messageId ? { messageId } : {}) }) },
      goBack: () => move(get().historyIndex - 1), goForward: () => move(get().historyIndex + 1),
      activateTab: id => { const tab = get().tabs.find(t => t.id === id); if (tab) navigate(tab.panel) },
      closeTab: id => {
        const s = get(), closed = s.tabs.find(t => t.id === id)
        if (!closed) return
        const tabs = s.tabs.filter(t => t.id !== id)
        set({ tabs, closedTabs: [...s.closedTabs, closed.panel].slice(-10) })
        if (s.activeTab === id) {
          const next = tabs.at(-1)
          if (next) navigate(next.panel)
          else { set({ rightPanel: { mode: 'evidence' }, activeTab: '', reading: s.readingMode === 'follow' ? null : s.reading }); layoutStore.setState({ right: false, full: false }) }
        }
      },
      closeOtherTabs: () => { const s = get(); set({ tabs: s.tabs.filter(t => t.id === s.activeTab), closedTabs: [...s.closedTabs, ...s.tabs.filter(t => t.id !== s.activeTab).map(t => t.panel)].slice(-10) }) },
      reopenTab: () => { const s = get(), panel = s.closedTabs.at(-1); if (panel) { set({ closedTabs: s.closedTabs.slice(0, -1) }); navigate(panel) } },
      setPinned: pinned => set({ pinned, ...(pinned ? { followEvidence: false } : {}) }),
      setFollowEvidence: followEvidence => set({ followEvidence, ...(followEvidence ? { pinned: false } : {}) }),
      notifyEvidence: () => {
        const s = get(); set({ newEvidence: true })
        if (s.followEvidence && !s.pinned && layoutStore.getState().right) { display({ mode: 'evidence' }); set({ newEvidence: false }) }
      },
      returnToCode: () => {
        const s = get()
        for (let i = s.historyIndex - 1; i >= 0; i--) if (['file', 'symbol'].includes(s.history[i].panel.mode)) { move(i); return }
        if (s.selectedPath) get().selectFile(s.selectedPath)
      },
      setReading: reading => {
        if (reading === null) set({ reading: null, readingMode: 'none' })
        else if (get().readingMode === 'follow') set({ reading })
      },
      fixReading: reading => set(s => ({ reading: reading ?? s.reading, readingMode: 'fixed' })),
      followReading: () => { set({ readingMode: 'follow', reading: null }); set(s => ({ rightPanel: { ...s.rightPanel } })) },
      saveScroll: (key, position) => set(s => ({ scrollPositions: { ...s.scrollPositions, [key]: position } })),
      resetProject: () => set(empty()),
      toggleDir: path => set(s => ({ expandedDirs: { ...s.expandedDirs, [path]: !s.expandedDirs[path] } })),
      toggleFile: path => set(s => ({ expandedFiles: { ...s.expandedFiles, [path]: !s.expandedFiles[path] } })),
      setTreeFilter: treeFilter => set({ treeFilter }),
    }
  })
  let workspaceKey: string | null = null
  let activation = 0
  function suspendWorkbench() { workspaceKey = null; activation++; workbenchStore.getState().resetProject(); viewStore.getState().reset() }
  async function activateWorkbench(key: string) {
    const generation = ++activation
    workspaceKey = null
    const snapshot = await readLocal<{ workbench: Partial<WorkbenchStore>; view: object }>(`workspace:${key}`)
    if (generation !== activation) return
    workbenchStore.getState().resetProject()
    viewStore.getState().reset()
    if (snapshot?.workbench && Array.isArray(snapshot.workbench.tabs) && Array.isArray(snapshot.workbench.history)) {
      workbenchStore.setState(snapshot.workbench)
      viewStore.setState(snapshot.view)
    }
    workspaceKey = key
  }
  function persistWorkspace() {
    if (!workspaceKey) return
    const snapshot = JSON.parse(JSON.stringify({ workbench: workbenchStore.getState(), view: viewStore.getState() }))
    void writeLocal(`workspace:${workspaceKey}`, snapshot)
  }
  workbenchStore.subscribe(persistWorkspace)
  viewStore.subscribe(persistWorkspace)
  return { workbenchStore, suspendWorkbench, activateWorkbench }
})
export const { workbenchStore, suspendWorkbench, activateWorkbench } = workspace
