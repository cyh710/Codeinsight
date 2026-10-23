import type { ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md' | 'lg'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** primary = 主操作（主题强调色实底）；secondary = 次操作（白底描边）；ghost = 密集区弱操作；danger = 破坏性操作。 */
  variant?: Variant
  /** sm = 32px 密集；md = 36px 默认；lg = 40px 主操作（§5.2 控件规范）。 */
  size?: Size
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: 'bg-accent font-medium text-accent-foreground shadow-sm hover:bg-accent-hover',
  secondary: 'border border-slate-200 bg-white font-medium text-slate-700 hover:bg-slate-50',
  ghost: 'font-medium text-slate-600 hover:bg-slate-200/60 hover:text-slate-900',
  danger: 'border border-red-200 bg-white font-medium text-red-600 hover:bg-red-50',
}

const SIZE_CLASSES: Record<Size, string> = {
  sm: 'h-8 px-3 text-xs',
  md: 'h-9 px-4 text-sm',
  lg: 'h-10 px-5 text-sm',
}

/**
 * 统一按钮（P2-1）：收敛全站 5 种按钮高度到 3 档、圆角统一 rounded-lg
 * （§5.1 控件圆角约定）。已有 class 串的旧按钮可在触达时逐步迁移。
 * 焦点环走 index.css 全局 ：focus-visible。
 * 按压触感（motion §2）：hover 颜色/阴影 150ms，按下 scale .98 80ms、
 * 松开 150ms 恢复——"按起来软"，不做 bounce/大缩放；主按钮 hover 轻抬 1px。
 */
export default function Button({
  variant = 'secondary',
  size = 'md',
  type = 'button',
  className = '',
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={`motion-press ${variant === 'primary' ? 'motion-press-lift ' : ''}inline-flex shrink-0 items-center justify-center gap-1.5 rounded-lg disabled:cursor-not-allowed disabled:opacity-45 ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}
