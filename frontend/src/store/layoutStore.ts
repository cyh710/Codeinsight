import { createStore } from 'zustand'
import { persistenceStore } from './persistence'

interface Layout {
  left: boolean; right: boolean; full: boolean; leftWidth: number; rightWidth: number
  sidebar: 'conversations' | 'files'; viewport: number
  toggleLeft: () => void; toggleRight: () => void; showRight: () => void
  toggleFull: () => void; resize: (side: 'left' | 'right', width: number) => void
  dragSidebar: (side: 'left' | 'right', width: number, opening: boolean) => void
  reset: () => void; setSidebar: (sidebar: 'conversations' | 'files') => void
  setViewport: (viewport: number) => void
}
const viewport = typeof innerWidth === 'number' ? innerWidth : 1440
const defaults = () => ({ left: (typeof innerWidth === 'number' ? innerWidth : 1440) >= 1280, right: (typeof innerWidth === 'number' ? innerWidth : 1440) >= 1100, full: false, leftWidth: 256, rightWidth: 480, sidebar: 'conversations' as const })
function saved() {
  try {
    const raw = JSON.parse(localStorage.getItem('ci.layout.v1') || '{}')
    return { ...defaults(), ...raw, full: false,
      leftWidth: Math.max(220, Math.min(360, Number(raw.leftWidth) || 256)),
      rightWidth: Math.max(360, Math.min(720, Number(raw.rightWidth) || 480)),
      sidebar: raw.sidebar === 'files' ? 'files' as const : 'conversations' as const }
  } catch { return defaults() }
}
export const layoutStore = createStore<Layout>((set) => ({
  ...saved(), viewport,
  toggleLeft: () => set((s) => ({ left: !s.left, full: false })),
  toggleRight: () => set((s) => ({ right: !s.right, full: false })),
  showRight: () => set({ right: true }),
  toggleFull: () => set((s) => ({ full: !s.full, right: true })),
  resize: (side, width) => set(side === 'left'
    ? { leftWidth: Math.max(220, Math.min(360, width)) }
    : { rightWidth: Math.max(360, Math.min(720, width)) }),
  dragSidebar: (side, width, opening) => set(() => {
    // 关闭时保留上次宽度；重新展开后再进入正常的尺寸调整。
    if (width < (opening ? 48 : 64)) return side === 'left'
      ? { left: false }
      : { right: false, full: false }
    return side === 'left'
      ? { left: true, full: false, leftWidth: Math.max(220, Math.min(360, width)) }
      : { right: true, full: false, rightWidth: Math.max(360, Math.min(720, width)) }
  }),
  reset: () => set(defaults()), setSidebar: (sidebar) => set({ sidebar }),
  setViewport: (viewport) => set((s) => ({ viewport, ...(viewport < 1280 && s.viewport >= 1280 ? { left: false } : {}) })),
}))
layoutStore.subscribe((state) => {
  if (typeof localStorage === 'undefined') return
  try {
    const { left, right, leftWidth, rightWidth, sidebar } = state
    localStorage.setItem('ci.layout.v1', JSON.stringify({ left, right, leftWidth, rightWidth, sidebar }))
  } catch { persistenceStore.setState({ error: '布局偏好保存失败，刷新后可能恢复默认布局。' }) }
})
