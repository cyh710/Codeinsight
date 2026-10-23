import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react'
import { createPortal } from 'react-dom'
import { Check, ChevronDown } from 'lucide-react'
import { parseOptionChildren, type SelectOption } from './selectOptions'

export interface SelectChangeEvent {
  target: { value: string; name?: string }
}

interface SelectProps {
  value: string
  onChange?: (event: SelectChangeEvent) => void
  children: ReactNode
  disabled?: boolean
  name?: string
  /** 无可见标签时的读屏名称；也兼容调用方直接传 aria-label。 */
  label?: string
  'aria-label'?: string
  /**
   * 作用于外层包装（决定控件的宽度布局，如 w-full / flex-1 / min-w-*）。
   * 触发器恒为 h-9 w-full，选中文案 truncate——控件尺寸与选项文本长度无关。
   */
  className?: string
}

/** 全局规则（ADR 0017）：面板最多完整显示 7 行，第 8 项起进入限高滚动窗口。 */
const MAX_VISIBLE_ROWS = 7
const ROW_HEIGHT = 36 // h-9 行高
const PANEL_PADDING = 12 // p-1.5 上下内边距
const PANEL_GAP = 6

/**
 * 统一下拉框（ADR 0017）：自绘 listbox，portal 渲染 + fixed 定位，
 * 面板限高 7 行、超出即滚动窗口（scrollbar-clean）；完整键盘导航
 * （↑↓ 跳过停用项 / Home / End / Enter / Esc / Tab），选中项带 Check。
 * API 与原生 select 兼容：调用方继续写 `<option>` children，onChange 仍收
 * `event.target.value`。焦点环走 index.css 全局 ：focus-visible。
 */
export default function Select({
  value,
  onChange,
  children,
  disabled = false,
  name,
  label,
  'aria-label': ariaLabel,
  className = '',
}: SelectProps) {
  const items = useMemo(() => parseOptionChildren(children), [children])
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const [position, setPosition] = useState<{ left: number; top: number; width: number; up: boolean } | null>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLUListElement>(null)
  const listId = useId()

  const selected = items.find((item) => item.value === value)
  const selectedIndex = Math.max(0, items.findIndex((item) => item.value === value))
  const screenName = label ?? ariaLabel

  const close = useCallback((refocus = false) => {
    setOpen(false)
    setPosition(null)
    if (refocus) triggerRef.current?.focus()
  }, [])

  const openList = useCallback(() => {
    if (disabled || items.length === 0) return
    const rect = triggerRef.current?.getBoundingClientRect()
    if (!rect) return
    const height = Math.min(items.length, MAX_VISIBLE_ROWS) * ROW_HEIGHT + PANEL_PADDING
    const spaceBelow = window.innerHeight - rect.bottom
    const up = spaceBelow < height + PANEL_GAP && rect.top > spaceBelow
    const width = Math.max(rect.width, 176)
    const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8))
    setActiveIndex(selectedIndex)
    setPosition({ left, width, top: up ? rect.top - height - PANEL_GAP : rect.bottom + PANEL_GAP, up })
    setOpen(true)
  }, [disabled, items.length, selectedIndex])

  // 外点、面板外滚动、窗口缩放都关闭；面板自身的滚动是限高窗口的正常行为。
  useEffect(() => {
    if (!open) return
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node
      if (triggerRef.current?.contains(target) || panelRef.current?.contains(target)) return
      close()
    }
    const handleDismiss = (event: Event) => {
      if (event.type === 'scroll' && panelRef.current?.contains(event.target as Node)) return
      close()
    }
    document.addEventListener('pointerdown', handlePointerDown)
    window.addEventListener('scroll', handleDismiss, true)
    window.addEventListener('resize', handleDismiss)
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      window.removeEventListener('scroll', handleDismiss, true)
      window.removeEventListener('resize', handleDismiss)
    }
  }, [open, close])

  useEffect(() => {
    if (open) panelRef.current?.focus({ preventScroll: true })
  }, [open])

  useEffect(() => {
    if (!open || activeIndex < 0) return
    panelRef.current?.querySelector(`[data-index="${activeIndex}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [open, activeIndex])

  // 从 from 出发按 delta 找第一个可用项，环形绕行；全停用时原地不动。
  const step = (from: number, delta: number) => {
    if (items.length === 0) return 0
    let index = from
    for (let i = 0; i < items.length; i += 1) {
      index = (index + delta + items.length) % items.length
      if (!items[index].disabled) return index
    }
    return from
  }

  const commit = (item: SelectOption | undefined) => {
    if (!item || item.disabled) return
    onChange?.({ target: { value: item.value, name } })
    close(true)
  }

  const onTriggerKeyDown = (event: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return
    if (!open && (event.key === 'ArrowDown' || event.key === 'ArrowUp' || event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault()
      openList()
    }
  }

  const onPanelKeyDown = (event: ReactKeyboardEvent<HTMLUListElement>) => {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault(); setActiveIndex((current) => step(current, 1)); break
      case 'ArrowUp':
        event.preventDefault(); setActiveIndex((current) => step(current, -1)); break
      case 'Home':
        event.preventDefault(); setActiveIndex(step(-1, 1)); break
      case 'End':
        event.preventDefault(); setActiveIndex(step(0, -1)); break
      case 'Enter':
      case ' ':
        event.preventDefault(); commit(items[activeIndex]); break
      case 'Escape':
        event.preventDefault(); close(true); break
      case 'Tab':
        close(); break
    }
  }

  return (
    <span className={`relative block ${className}`}>
      <button
        type="button"
        ref={triggerRef}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={screenName}
        onClick={() => (open ? close() : openList())}
        onKeyDown={onTriggerKeyDown}
        className={`flex h-9 w-full items-center justify-between gap-2 rounded-lg border bg-white/70 pl-3 pr-2.5 text-left text-sm text-slate-700 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-50 ${open ? 'border-accent-bright' : 'border-slate-200'}`}
      >
        <span className="block truncate">{selected ? selected.label : value}</span>
        <ChevronDown
          size={16}
          strokeWidth={1.5}
          aria-hidden="true"
          className={`shrink-0 text-slate-500 transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && position && createPortal(
        <ul
          ref={panelRef}
          role="listbox"
          aria-label={screenName}
          aria-activedescendant={items[activeIndex] ? `${listId}-${activeIndex}` : undefined}
          tabIndex={-1}
          onKeyDown={onPanelKeyDown}
          data-open-up={position.up}
          style={{
            left: position.left,
            top: position.top,
            width: position.width,
            maxHeight: Math.min(items.length, MAX_VISIBLE_ROWS) * ROW_HEIGHT + PANEL_PADDING,
          }}
          className="select-panel-in fixed z-[120] overflow-y-auto rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl scrollbar-clean focus:outline-none"
        >
          {items.map((item, index) => {
            const rowState = item.disabled
              ? 'cursor-not-allowed text-slate-300'
              : item.value === value
                ? 'bg-accent-soft font-semibold text-slate-900'
                : index === activeIndex
                  ? 'bg-slate-100 text-slate-900'
                  : 'text-slate-600'
            return (
              <li
                key={item.value}
                id={`${listId}-${index}`}
                role="option"
                aria-selected={item.value === value}
                aria-disabled={item.disabled || undefined}
                data-index={index}
                onMouseMove={() => { if (!item.disabled) setActiveIndex(index) }}
                onClick={() => commit(item)}
                className={`flex h-9 cursor-pointer items-center justify-between gap-2 rounded-lg px-2.5 text-sm ${rowState}`}
              >
                <span className="block truncate">{item.label}</span>
                {item.value === value && <Check size={14} strokeWidth={2} aria-hidden="true" className="shrink-0 text-accent" />}
              </li>
            )
          })}
        </ul>,
        document.body,
      )}
    </span>
  )
}

