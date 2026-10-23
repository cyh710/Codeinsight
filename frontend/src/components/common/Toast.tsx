import { useState, type AnimationEvent, type ReactNode } from 'react'
import { usePresence } from './Presence'

interface ToastProps {
  /** 当前要展示的文案；清空即触发退出动画，动画结束后停止渲染。 */
  message: ReactNode
  /** 定位与外观类（位置由宿主决定，本原语只管出入场运动）。 */
  className?: string
}

/**
 * 最小 Toast 原语（motion §11）：进入 opacity 0 + translateY(-6px) → 0
 * （220ms）；退出 translateY(-4px) + 淡出（150ms），由 Presence 原语保证
 * 退出动画播完才卸载。连续通知只换文案、不重播入场。
 * Error 用颜色 + icon 表达（不做大幅 shake），Success check 由
 * .motion-pop-in 承担——都在调用方内容里。
 */
export default function Toast({ message, className = '' }: ToastProps) {
  const open = Boolean(message)
  // 退出兜底 300ms > 退出动画 150ms，留足余量。
  const { mounted, exiting, finishExit } = usePresence(open, 300)
  // 退出动画期间保留最后一条文案，避免文字先于容器消失。
  const [shown, setShown] = useState(message)
  const [prevMessage, setPrevMessage] = useState(message)
  // 渲染期护栏调整（同 Presence）：message 有值就同步展示内容。
  if (prevMessage !== message) {
    setPrevMessage(message)
    if (message) setShown(message)
  }
  if (!mounted || !shown) return null

  // React 合成事件随卸载自动清理；target 过滤子元素动画冒泡。
  const handleAnimationEnd = (event: AnimationEvent<HTMLDivElement>) => {
    if (!exiting) return
    if (event.target !== event.currentTarget) return
    finishExit()
  }

  return (
    <div
      role="status"
      onAnimationEnd={handleAnimationEnd}
      className={`motion-toast ${exiting ? 'motion-toast-exit' : ''} ${className}`}
    >
      {shown}
    </div>
  )
}
