/**
 * 动效纯函数助手（docs/tasks/2026-09-10-system-motion.md §9）。
 *
 * 列表 stagger 上限：Card N = (N-1)×25ms，最多前 6 个有延迟，第 7 个起
 * 全部立即出现（0ms）。只应在"真正首次加载"时套用，搜索/排序/流式更新
 * 不得重播（调用方用一次性开关控制）。
 */

export const STAGGER_STEP_MS = 25
export const STAGGER_CAP_ITEMS = 6

/** 第 index 个卡片的入场延迟（ms）；超出上限或非法输入一律 0（立即出现）。 */
export function staggerDelayMs(index: number, step = STAGGER_STEP_MS, cap = STAGGER_CAP_ITEMS): number {
  if (!Number.isInteger(index) || index < 0 || index >= cap) return 0
  return index * step
}
