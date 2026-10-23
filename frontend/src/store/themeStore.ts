import { createStore } from 'zustand'
import {
  DEFAULT_PALETTE_ID,
  getPalette,
  hexToRgbChannels,
  normalizePaletteId,
  paletteCssVars,
  type PaletteId,
} from '../theme/palettes'

export interface ThemeStore {
  paletteId: PaletteId
  backgroundUrl: string
  backgroundOpacity: number
  bubbleFrameOpacity: number
  sidebarOpacity: number
  avatars: Record<string, string>
  characterBackgrounds: Record<string, string>
  setPaletteId: (id: PaletteId) => void
  setBackground: (url: string) => void
  setBackgroundOpacity: (opacity: number) => void
  setBubbleFrameOpacity: (opacity: number) => void
  setSidebarOpacity: (opacity: number) => void
  setAvatar: (character: string, url: string) => void
  setCharacterBackground: (character: string, url: string) => void
  /** Remove only role-scoped presentation state; global theme remains intact. */
  clearCharacterAssets: (character: string) => void
}

type PersistedTheme = Pick<ThemeStore, 'paletteId' | 'backgroundUrl' | 'backgroundOpacity' | 'bubbleFrameOpacity' | 'sidebarOpacity' | 'avatars' | 'characterBackgrounds'>

function loadFromStorage(): Partial<PersistedTheme> {
  try {
    const raw = localStorage.getItem('ai-companion-theme')
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return {}
}

function saveToStorage(state: {
  paletteId: PaletteId
  backgroundUrl: string
  backgroundOpacity: number
  bubbleFrameOpacity: number
  sidebarOpacity: number
  avatars: Record<string, string>
  characterBackgrounds: Record<string, string>
}) {
  localStorage.setItem('ai-companion-theme', JSON.stringify({
    paletteId: state.paletteId,
    backgroundUrl: state.backgroundUrl,
    backgroundOpacity: state.backgroundOpacity,
    bubbleFrameOpacity: state.bubbleFrameOpacity,
    sidebarOpacity: state.sidebarOpacity,
    avatars: state.avatars,
    characterBackgrounds: state.characterBackgrounds,
  }))
}

let bubblePersistTimer: ReturnType<typeof setTimeout> | null = null

function scheduleThemePersist(getState: () => {
  paletteId: PaletteId
  backgroundUrl: string
  backgroundOpacity: number
  bubbleFrameOpacity: number
  sidebarOpacity: number
  avatars: Record<string, string>
  characterBackgrounds: Record<string, string>
}) {
  // Range inputs can emit dozens of events per second.  localStorage is
  // synchronous, so writing on every event blocks the main thread exactly
  // while the user is dragging the bubble-opacity slider.
  if (bubblePersistTimer) clearTimeout(bubblePersistTimer)
  bubblePersistTimer = setTimeout(() => {
    bubblePersistTimer = null
    // 读最新全量状态序列化：延迟写入不能拿旧快照覆盖中途的新主题选择。
    saveToStorage(getState())
  }, 120)
}

/** 把当前主题的品牌变量写到根节点（只更新 CSS 变量，不触发 React 重渲染）。 */
function applyPalette(paletteId: PaletteId) {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  const vars = paletteCssVars(getPalette(paletteId))
  for (const [name, value] of Object.entries(vars)) {
    root.style.setProperty(name, value)
  }
}

function syncBubbleCss(opacity: number, paletteId: PaletteId = DEFAULT_PALETTE_ID) {
  if (typeof document === 'undefined') return
  const frame = Math.min(Math.max(Number(opacity) || 0, 0), 1)
  // P0-1 可读性下限："融入背景"不允许把白色拉到 55% 以下——
  // 低于该值时气泡文字（slate-800）压深色背景会跌破 WCAG AA。
  const MIN_SCRIM = 0.56
  const root = document.documentElement
  const channels = hexToRgbChannels(getPalette(paletteId).accent) ?? [3, 105, 161]
  const [accentR, accentG, accentB] = channels
  const shadow = frame < 0.04
    ? 'none'
    : `0 ${4 + frame * 8}px ${10 + frame * 24}px rgba(15, 23, 42, ${0.04 + frame * 0.12})`
  const blur = frame < 0.04 ? 'none' : `blur(${Math.round(1 + frame * 8)}px)`
  const bubbleBackground = MIN_SCRIM + frame * 0.4
  const bubbleBorder = 0.08 + frame * 0.42
  // 用户气泡锁死实色（当前主题功能色）：白字 ≥4.5:1，不随滑块变化（ADR 0009/0013）
  root.style.setProperty('--chat-bubble-user-background', `rgb(${accentR}, ${accentG}, ${accentB})`)
  root.style.setProperty('--chat-bubble-background', `rgba(255, 255, 255, ${Math.min(bubbleBackground, 0.98)})`)
  // A lightly tinted border remains visible against both photos and pale UI
  // surfaces; its strength is what the slider communicates as “边框清晰”.
  root.style.setProperty('--chat-bubble-border', `rgba(${accentR}, ${accentG}, ${accentB}, ${bubbleBorder})`)
  root.style.setProperty('--chat-bubble-shadow', shadow)
  root.style.setProperty('--chat-bubble-filter', blur)
}

const saved = loadFromStorage()

export const themeStore = createStore<ThemeStore>((set, get) => ({
  paletteId: normalizePaletteId(saved.paletteId),
  backgroundUrl: saved.backgroundUrl || '',
  backgroundOpacity: saved.backgroundOpacity ?? 0.85,
  bubbleFrameOpacity: saved.bubbleFrameOpacity ?? 0.28,
  sidebarOpacity: saved.sidebarOpacity ?? 0.62,
  avatars: saved.avatars || {},
  characterBackgrounds: saved.characterBackgrounds || {},

  setPaletteId: (id) => {
    const paletteId = normalizePaletteId(id)
    set({ paletteId })
    // set() 已同步触发订阅刷新气泡颜色；这里补齐主题变量并立即持久化。
    applyPalette(paletteId)
    saveToStorage(get())
  },

  setBackground: (url) => {
    set({ backgroundUrl: url })
    saveToStorage(get())
  },

  setBackgroundOpacity: (opacity) => {
    set({ backgroundOpacity: opacity })
    saveToStorage(get())
  },

  setBubbleFrameOpacity: (opacity) => {
    set({ bubbleFrameOpacity: opacity })
    syncBubbleCss(opacity, get().paletteId)
    scheduleThemePersist(get)
  },

  setSidebarOpacity: (opacity) => {
    set({ sidebarOpacity: opacity })
    saveToStorage(get())
  },

  setAvatar: (character, url) => {
    const avatars = { ...get().avatars }
    if (url) avatars[character] = url
    else delete avatars[character]
    set({ avatars })
    saveToStorage(get())
  },

  setCharacterBackground: (character, url) => {
    if (!character) return
    const characterBackgrounds = { ...get().characterBackgrounds }
    if (url) characterBackgrounds[character] = url
    else delete characterBackgrounds[character]
    set({ characterBackgrounds })
    saveToStorage(get())
  },

  clearCharacterAssets: (character) => {
    if (!character) return
    const avatars = { ...get().avatars }
    const characterBackgrounds = { ...get().characterBackgrounds }
    let changed = false
    if (Object.prototype.hasOwnProperty.call(avatars, character)) {
      delete avatars[character]
      changed = true
    }
    if (Object.prototype.hasOwnProperty.call(characterBackgrounds, character)) {
      delete characterBackgrounds[character]
      changed = true
    }
    if (!changed) return
    set({ avatars, characterBackgrounds })
    saveToStorage(get())
  },
}))

// Theme variables go on first paint (module init happens before React render).
applyPalette(themeStore.getState().paletteId)

// Keep chat bubbles on a CSS-variable path.  The slider updates this single
// style declaration instead of forcing every historical Markdown bubble to
// render again on every pointer event.
syncBubbleCss(themeStore.getState().bubbleFrameOpacity, themeStore.getState().paletteId)
themeStore.subscribe((state) => syncBubbleCss(state.bubbleFrameOpacity, state.paletteId))
