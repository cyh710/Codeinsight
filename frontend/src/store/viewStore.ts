/**
 * 中栏视图状态：对话 / 关系图 / 变更时间线。
 *
 * 单独成 store 的理由：右栏符号卡上的「在关系图中查看」要能切换**中栏**，
 * 而中栏组件反过来不拥有符号。放在 workbenchStore 会让「选中什么」和
 * 「看哪一屏」耦在一起；这里只记「看哪一屏、图以谁为中心」。
 */
import { createStore } from 'zustand'

export type CenterTab = 'chat' | 'graph' | 'timeline'

export interface ViewStore {
  timelineExpanded: string | null
  timelineScroll: number
  graphHistory: (string | null)[]
  graphMode: string
  setTimelineExpanded: (value: string | null | ((current: string | null) => string | null)) => void
  centerTab: CenterTab
  /** 关系图中心；null = 打开时的当前符号，仍没有就以概览图打开。 */
  graphFocus: string | null
  /** 每次「打开关系图」自增：已在图上时再点一次也要重新定位。 */
  graphRequest: number

  setCenterTab: (tab: CenterTab) => void
  openGraph: (qualname?: string | null) => void
  openTimeline: () => void
  setGraphFocus: (qualname: string | null) => void
  reset: () => void
}

export const viewStore = createStore<ViewStore>((set) => ({
  timelineExpanded: null, timelineScroll: 0, graphHistory: [], graphMode: 'reading',
  setTimelineExpanded: value => set(s => ({ timelineExpanded: typeof value === 'function' ? value(s.timelineExpanded) : value })),
  centerTab: 'chat',
  graphFocus: null,
  graphRequest: 0,

  setCenterTab: (tab) => set({ centerTab: tab }),
  openGraph: (qualname = null) =>
    set((s) => ({ centerTab: 'graph', graphFocus: qualname, graphRequest: s.graphRequest + 1 })),
  openTimeline: () => set({ centerTab: 'timeline' }),
  setGraphFocus: (qualname) => set({ graphFocus: qualname }),
  reset: () => set({ centerTab: 'chat', graphFocus: null, graphRequest: 0, timelineExpanded: null, timelineScroll: 0, graphHistory: [], graphMode: 'reading' }),
}))
