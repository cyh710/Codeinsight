import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

/** 浮层脱离阅读区的层叠上下文，避免被正文的固定工具条遮住。 */
export default function ActionMenu({ label, trigger, children, className = '' }: {
  label: string
  trigger: ReactNode
  children: (close: () => void) => ReactNode
  className?: string
}) {
  const [position, setPosition] = useState<{ top: number; right: number } | null>(null)
  const button = useRef<HTMLButtonElement>(null)
  const menu = useRef<HTMLDivElement>(null)
  const id = useId()
  const close = () => { setPosition(null); document.getElementById(`${id}-trigger`)?.focus() }
  useEffect(() => {
    if (!position) return
    const outside = (event: PointerEvent) => {
      if (!menu.current?.contains(event.target as Node) && !button.current?.contains(event.target as Node)) setPosition(null)
    }
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); setPosition(null); button.current?.focus() }
      if (event.key === 'Tab') setPosition(null)
    }
    const resize = () => setPosition(null)
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', keydown)
    window.addEventListener('resize', resize)
    menu.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus()
    return () => {
      document.removeEventListener('pointerdown', outside)
      document.removeEventListener('keydown', keydown)
      window.removeEventListener('resize', resize)
    }
  }, [position])
  return <>
    <button id={`${id}-trigger`} ref={button} type="button" className={`wb-icon-button ${className}`} aria-label={label}
      title={label} aria-haspopup="menu" aria-expanded={Boolean(position)} aria-controls={position ? id : undefined}
      onClick={() => {
        if (position) { setPosition(null); return }
        const rect = button.current!.getBoundingClientRect()
        setPosition({ top: Math.min(rect.bottom + 5, innerHeight - 250), right: Math.max(8, Math.min(innerWidth - rect.right, innerWidth - 248)) })
      }}>{trigger}</button>
    {position && createPortal(<div id={id} ref={menu} role="menu" aria-label={label} className="wb-action-menu"
      style={{ top: Math.max(8, position.top), right: position.right }}
      onKeyDown={event => {
        if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
        event.preventDefault()
        const items = [...menu.current!.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled)')]
        const index = items.indexOf(document.activeElement as HTMLElement)
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length
        items[next]?.focus()
      }}>{children(close)}</div>, document.body)}
  </>
}
