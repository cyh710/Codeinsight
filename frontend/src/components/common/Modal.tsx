import { useEffect, useId, useRef, type AnimationEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { usePresence } from './Presence'

// A confirmation dialog can be opened above a larger settings dialog. Keep a
// small stack so only the topmost modal handles keyboard events and the body
// scroll lock is released after the final modal closes.
const modalStack: symbol[] = []
let bodyOverflowBeforeModal: string | null = null

function removeModal(id: symbol) {
  const index = modalStack.indexOf(id)
  if (index >= 0) modalStack.splice(index, 1)
}

/** 每用途运动变体（motion §3）：不同空间关系不同运动方向。 */
export type ModalMotion = 'default' | 'drawer-left' | 'drawer-right'

const PANEL_MOTION_CLASS: Record<ModalMotion, string> = {
  default: 'modal-panel',
  'drawer-left': 'modal-panel modal-panel-drawer-left',
  'drawer-right': 'modal-panel modal-panel-drawer-right',
}

interface ModalProps {
  open: boolean
  onClose: () => void
  /** 卡片标题；bare 模式下忽略 */
  title?: ReactNode
  children: ReactNode
  /**
   * 面板宽度类（Tailwind max-w-*）。bare=false 时套默认白色卡片。
   * bare=true 时 Modal 只提供遮罩 + ESC + 焦点管理，面板布局完全由 children 决定
   * （供设置/记忆/桌宠工作台等大面板复用）。
   */
  widthClass?: string
  bare?: boolean
  /** 遮罩点击是否关闭；默认开启。输入型弹窗可关掉防误触。 */
  closeOnBackdrop?: boolean
  /** 遮罩样式覆盖（默认黑色半透明） */
  backdropClass?: string
  /** 无标题（bare）面板使用的可访问名称。 */
  ariaLabel?: string
  /**
   * 层级类覆盖。默认 z-[90]：弹窗天生要压过应用设置弹窗与桌宠工作台
   * （宿主 z-[80]）——默认 z-50 的年代，凡忘传 zClass 的弹层在这两个宿主里
   * 都会被整个盖住（"按钮按了没反应"）。需要低于默认层级的场景才显式传。
   */
  zClass?: string
  /** bare 模式下面板容器的额外类（如右侧抽屉的 ml-auto h-full） */
  panelClass?: string
  /**
   * 运动变体（motion §3）：default = 居中弹窗（缩放+上浮）；
   * drawer-left / drawer-right = 侧栏抽屉（从对应侧滑入 20px + 半透明起步，
   * 退出反向滑回），不使用缩放。
   */
  motion?: ModalMotion
}

/**
 * 统一弹窗原语：portal 到 body、ESC 关闭、遮罩淡入、面板入场、
 * 打开时焦点移入面板、关闭时焦点归还触发元素。
 * 关闭走 Presence 原语（motion §3）：先播 150ms 退出动画
 * （.modal-exiting，期间 pointer-events 关闭），animationend 后才真正卸载；
 * ESC/模态栈/滚动锁在 open 翻 false 的当下立即释放，与动画无关。
 * 所有动画遵守全局 prefers-reduced-motion 降级（见 index.css）。
 */
export default function Modal({
  open,
  onClose,
  title,
  children,
  widthClass = 'max-w-lg',
  bare = false,
  closeOnBackdrop = true,
  backdropClass = 'bg-black/30',
  ariaLabel,
  zClass = 'z-[90]',
  panelClass = '',
  motion = 'default',
}: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  // P0-2 模态语义：读屏播报"进入对话框"所需的关联标题 id
  const titleId = useId()
  // 记住打开前的焦点元素，关闭时归还（键盘用户体验）
  const restoreFocusRef = useRef<HTMLElement | null>(null)
  const modalIdRef = useRef<symbol | null>(null)
  // Presence：退出动画窗口期保持挂载，动画结束后真正卸载。
  // 退出动画 150ms（--motion-fast），兜底计时器放宽到 400ms。
  const { mounted, exiting, finishExit } = usePresence(open, 400)
  // onClose 存 ref：调用方常用内联箭头函数，避免监听器随渲染反复重绑。
  // 在 effect 中同步，避免渲染期写 ref（react-hooks/refs）。
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  })

  useEffect(() => {
    if (!open) return
    const modalId = modalIdRef.current ?? Symbol('modal')
    modalIdRef.current = modalId
    modalStack.push(modalId)
    restoreFocusRef.current = document.activeElement as HTMLElement | null
    panelRef.current?.focus()
    // 锁定背景滚动：弹窗开着时背后的聊天区不应还能滚
    if (modalStack.length === 1) bodyOverflowBeforeModal = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const handleKeyDown = (event: KeyboardEvent) => {
      if (modalStack[modalStack.length - 1] !== modalId) return
      if (event.key === 'Escape') {
        event.preventDefault()
        // Prevent a parent modal's document listener from closing it in the
        // same key event when this dialog is stacked above it.
        event.stopImmediatePropagation()
        onCloseRef.current()
        return
      }
      // P0-2 焦点陷阱：Tab 循环限制在面板内，防止键盘落进被遮挡的聊天输入框
      if (event.key === 'Tab' && panelRef.current) {
        const focusables = panelRef.current.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])',
        )
        if (focusables.length === 0) return
        const first = focusables[0]
        const last = focusables[focusables.length - 1]
        const active = document.activeElement
        if (event.shiftKey && (active === first || !(active instanceof Node && panelRef.current.contains(active)))) {
          event.preventDefault()
          last.focus()
        } else if (!event.shiftKey && active === last) {
          event.preventDefault()
          first.focus()
        }
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      removeModal(modalId)
      if (modalStack.length === 0) {
        document.body.style.overflow = bodyOverflowBeforeModal ?? ''
        bodyOverflowBeforeModal = null
      }
      // 关闭时把焦点还给触发元素；元素可能已被卸载，做兜底判断
      const previous = restoreFocusRef.current
      if (previous && document.contains(previous)) previous.focus()
    }
  }, [open])

  if (!mounted) return null

  const dialogProps = {
    role: 'dialog' as const,
    'aria-modal': true,
    'aria-labelledby': title !== undefined ? titleId : undefined,
    'aria-label': title === undefined ? ariaLabel : undefined,
  }

  // 退出动画结束信号：React 合成事件随卸载自动清理。必须过滤子元素自己的
  // 动画冒泡（骨架屏 pulse 等），只在面板自身的 animationend 收尾。
  const handlePanelAnimationEnd = (event: AnimationEvent<HTMLDivElement>) => {
    if (!exiting) return
    if (event.target !== event.currentTarget) return
    finishExit()
  }

  return createPortal(
    <div
      className={`fixed inset-0 flex items-center justify-center p-4 modal-backdrop ${exiting ? 'modal-exiting' : ''} ${zClass} ${backdropClass}`}
      onClick={closeOnBackdrop ? onClose : undefined}
    >
      {bare ? (
        <div
          ref={panelRef}
          tabIndex={-1}
          {...dialogProps}
          onAnimationEnd={handlePanelAnimationEnd}
          className={`${PANEL_MOTION_CLASS[motion]} outline-none ${panelClass}`}
          onClick={(event) => event.stopPropagation()}
        >
          {children}
        </div>
      ) : (
        <div
          ref={panelRef}
          tabIndex={-1}
          {...dialogProps}
          onAnimationEnd={handlePanelAnimationEnd}
          className={`${PANEL_MOTION_CLASS[motion]} w-full ${widthClass} rounded-xl border border-slate-200 bg-white p-4 shadow-2xl outline-none`}
          onClick={(event) => event.stopPropagation()}
        >
          {title !== undefined && (
            <div className="mb-3 flex items-center justify-between">
              <h3 id={titleId} className="text-sm font-semibold text-slate-900">{title}</h3>
              <button
                type="button"
                onClick={onClose}
                aria-label="关闭"
                className="flex h-8 w-8 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-600"
              >
                <X size={16} strokeWidth={1.5} aria-hidden="true" />
              </button>
            </div>
          )}
          {children}
        </div>
      )}
    </div>,
    document.body,
  )
}
