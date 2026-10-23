import { useEffect, useState } from 'react'

/**
 * 延迟确认一个"进行中"标志：active 持续超过 delayMs 才返回 true。
 *
 * 用途：骨架屏防闪烁（UI_REVIEW A-8 / §5.3「加载 < 1s 不显示」）。加载在
 * 200ms 内完成时返回值始终为 false，骨架完全不进入 DOM；慢加载时先空白
 * 200ms 再出现骨架，而不是先骨架再内容地跳一下。
 *
 * active 变回 false 时在下一个宏任务复位（返回 false 且重新计时），允许
 * 列表在切换数据源时重复触发。状态翻转全部走定时器回调，不在 effect 体内
 * 同步 setState（react-hooks/set-state-in-effect）。
 */
export function useDelayedFlag(active: boolean, delayMs = 200): boolean {
  const [pastDelay, setPastDelay] = useState(false)

  useEffect(() => {
    const timer = window.setTimeout(() => setPastDelay(active), active ? delayMs : 0)
    return () => window.clearTimeout(timer)
  }, [active, delayMs])

  return active && pastDelay
}
