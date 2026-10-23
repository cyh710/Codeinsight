import { useCallback, useEffect, useState } from 'react'

/**
 * Presence 原语（docs/tasks/2026-09-10-system-motion.md §3）。
 *
 * React 的 `open` 布尔只能控制挂载/卸载，卸载发生在动画有机会播放之前，
 * 因此弹层默认"有进无出"。本原语补上极小的退出通道，不引入动画框架：
 *
 *   open=false → exiting（保持挂载，播放退出动画）
 *              → animationend（或兜底计时器）→ 真正卸载
 *
 * 挂载期间再次 open=true 会取消退出（exiting → open），内容原地保留。
 * 全部动画遵守 index.css 的 prefers-reduced-motion 全局降级——那时
 * animationend 几乎立即触发，行为等同直接卸载。
 */

export type PresencePhase = 'closed' | 'open' | 'exiting'

/**
 * 纯状态机（presence.test.ts 钉住）：
 * - closed + open → open（进入）
 * - open + close → exiting（开始退出，保持挂载）
 * - exiting + close → exiting（退出中不重启退出）
 * - exiting + open → open（退出被取消，取消卸载）
 */
export function presenceTransition(prev: PresencePhase, open: boolean): PresencePhase {
  if (open) return 'open'
  return prev === 'closed' ? 'closed' : 'exiting'
}

export interface PresenceResult {
  /** 是否渲染（false = 退出动画已结束，可以真正卸载子树）。 */
  mounted: boolean
  /** 是否处于退出播放期（调用方借此挂退出动画类 / 关闭交互）。 */
  exiting: boolean
  /**
   * 退出动画结束信号。接到面板动画的 animationend 时调用（React 合成事件
   * 随组件卸载自动清理，无需手动 removeEventListener）；注意用
   * `event.target === event.currentTarget` 过滤子元素动画的冒泡。
   */
  finishExit: () => void
}

/**
 * @param open 受控开关
 * @param exitMs 退出兜底时长（应略大于实际退出动画总时长）。animationend
 *   丢失（如面板被 display:none、事件被拦截）时由它保证最终一定卸载。
 */
export function usePresence(open: boolean, exitMs = 400): PresenceResult {
  const [phase, setPhase] = useState<PresencePhase>(() => presenceTransition('closed', open))
  // open 变化统一走状态机。这里用 React 官方的"渲染期依据 props 调整 state"
  // 模式（以 prevOpen 作护栏），而不是 effect 里 setState——后者会触发
  // 级联渲染，也被 react-hooks 新规直接拒绝。
  const [prevOpen, setPrevOpen] = useState(open)
  if (prevOpen !== open) {
    setPrevOpen(open)
    setPhase((prev) => presenceTransition(prev, open))
  }

  const finishExit = useCallback(() => {
    setPhase((prev) => (prev === 'exiting' ? 'closed' : prev))
  }, [])

  // 兜底计时器：animationend 是主信号，计时器只兜丢失场景。
  useEffect(() => {
    if (phase !== 'exiting') return
    const timer = window.setTimeout(finishExit, exitMs)
    return () => window.clearTimeout(timer)
  }, [phase, exitMs, finishExit])

  return { mounted: phase !== 'closed', exiting: phase === 'exiting', finishExit }
}
