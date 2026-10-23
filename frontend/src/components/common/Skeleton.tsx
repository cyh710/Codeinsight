/**
 * 骨架屏原语（UI 设计系统 T5a）。
 *
 * 基类：`bg-slate-200/70 animate-pulse`。`prefers-reduced-motion` 下全局 CSS
 * （index.css）会把动画压到 0.01ms，骨架自然退化为静态灰块，无需额外分支。
 *
 * 配套 hook `useDelayedFlag(active, 200)` 控制骨架延迟出现：加载快于 200ms
 * 时不渲染骨架，避免闪烁（见 archive/docs/UI_REVIEW_2026-09.md A-8）。
 *
 * 无障碍约定：骨架是纯装饰，组件自身 aria-hidden；接入处在 wrapped 容器上
 * 加 `role="status"` + `aria-label="正在加载…"`，读屏用户仍能听到加载状态。
 */

/** 基础灰块。圆角由调用方覆盖（传入 rounded-* 类即覆盖默认 rounded-lg）。 */
export default function Skeleton({ className = '' }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse rounded-lg bg-slate-200/70 ${className}`}
    />
  )
}

/** 多行文本骨架：默认 3 行，末行 60% 宽，模拟自然段落的收尾。 */
export function SkeletonText({
  lines = 3,
  className = '',
}: {
  lines?: number
  className?: string
}) {
  return (
    <div aria-hidden="true" className={`space-y-2 ${className}`}>
      {Array.from({ length: lines }, (_, index) => (
        <div
          key={index}
          className={`animate-pulse rounded-lg bg-slate-200/70 ${
            index === lines - 1 ? 'w-3/5' : 'w-full'
          } h-4`}
        />
      ))}
    </div>
  )
}

/** 卡片骨架：标题条 + 两行文本，外框沿用卡片规范（rounded-xl + 细描边）。 */
export function SkeletonCard({ className = '' }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`rounded-xl border border-slate-200/70 bg-white/40 p-3 ${className}`}
    >
      <div className="animate-pulse h-4 w-1/3 rounded-lg bg-slate-200/70" />
      <div className="mt-2 space-y-1.5">
        <div className="animate-pulse h-3 w-full rounded-lg bg-slate-200/70" />
        <div className="animate-pulse h-3 w-3/5 rounded-lg bg-slate-200/70" />
      </div>
    </div>
  )
}

/** 头像骨架：圆形。尺寸由调用方给（默认 h-10 w-10）。 */
export function SkeletonAvatar({
  className = 'h-10 w-10',
}: {
  className?: string
}) {
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse h-10 w-10 rounded-full bg-slate-200/70 ${className}`}
    />
  )
}
