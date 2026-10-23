import type { ReactNode } from 'react'

interface ChipProps {
  children: ReactNode
  /** 开关态（仅 onToggle / as="button" 时生效为样式与 aria-pressed）。 */
  selected?: boolean
  /** 传入即渲染为开关按钮：带状态点 + aria-pressed，点击触发。 */
  onToggle?: () => void
  /** "button" 渲染为按钮（触发器形态，无状态点，透传 aria-pressed）；默认按 onToggle 推断，否则纯展示 span。 */
  as?: 'span' | 'button'
  disabled?: boolean
  title?: string
  className?: string
}

/**
 * 统一 chip（P2-1 / A-6）：h-9 rounded-full px-3 text-xs，与发送按钮同高。
 * - 开关（传 onToggle）：选中 `border-accent bg-accent text-accent-foreground` +
 *   状态点（开=浅色点/关=灰点），不靠增删"开"字表达状态，避免字宽抖动。
 * - 触发器（as="button" 无 onToggle）：同外形，无状态点，可加箭头等 children。
 * - 纯展示（默认）：span 徽章。
 */
export default function Chip({
  children,
  selected = false,
  onToggle,
  as,
  disabled = false,
  title,
  className = '',
}: ChipProps) {
  const interactive = as === 'button' || Boolean(onToggle)
  const stateClasses = selected
    ? 'border-accent bg-accent font-medium text-accent-foreground shadow-sm hover:bg-accent-hover'
    : 'border-slate-300 bg-white/80 text-slate-600 hover:bg-white'
  // 交互态走 motion-press（motion §2：按下 80ms scale .98，松开 150ms 恢复）；
  // 纯展示 span 不参与按压，保留颜色过渡即可。
  const classes = `${
    interactive ? 'motion-press' : 'transition-colors'
  } flex h-9 items-center gap-1.5 rounded-full border px-3 text-xs disabled:cursor-not-allowed disabled:opacity-50 ${stateClasses} ${className}`

  if (!interactive) {
    return (
      <span title={title} className={classes}>
        {children}
      </span>
    )
  }
  return (
    <button
      type="button"
      disabled={disabled}
      title={title}
      onClick={onToggle}
      aria-pressed={selected}
      className={classes}
    >
      {onToggle && (
        <span
          aria-hidden="true"
          className={`h-2 w-2 rounded-full ${selected ? 'bg-accent-soft' : 'bg-slate-400'}`}
        />
      )}
      {children}
    </button>
  )
}
