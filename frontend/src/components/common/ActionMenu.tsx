import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { usePresence } from './Presence'

/** 浮层脱离阅读区的层叠上下文，避免被正文的固定工具条遮住。 */
export default function ActionMenu({ label, trigger, children, className = '', menuClassName = '' }: {
  label: string
  trigger: ReactNode
  children: (close: () => void) => ReactNode
  className?: string
  menuClassName?: string
}) {
  const [position, setPosition] = useState<{ top: number; right: number } | null>(null)
  const [open, setOpen] = useState(false)
  const { mounted, exiting, finishExit } = usePresence(open, 180)
  const button = useRef<HTMLButtonElement>(null)
  const menu = useRef<HTMLDivElement>(null)
  const id = useId()
  const close = () => { setOpen(false); document.getElementById(`${id}-trigger`)?.focus() }
  useEffect(() => {
    if (!open) return
    const outside = (event: PointerEvent) => {
      if (!menu.current?.contains(event.target as Node) && !button.current?.contains(event.target as Node)) setOpen(false)
    }
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); setOpen(false); button.current?.focus() }
      if (event.key === 'Tab') setOpen(false)
    }
    const resize = () => setOpen(false)
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', keydown)
    window.addEventListener('resize', resize)
    menu.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus()
    return () => {
      document.removeEventListener('pointerdown', outside)
      document.removeEventListener('keydown', keydown)
      window.removeEventListener('resize', resize)
    }
  }, [open, position])
  return <>
    <button id={`${id}-trigger`} ref={button} type="button" className={`wb-icon-button ${className}`} aria-label={label}
      title={label} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined}
      onClick={() => {
        if (open) { setOpen(false); return }
        const rect = button.current!.getBoundingClientRect()
        setPosition({ top: Math.min(rect.bottom + 5, innerHeight - 250), right: Math.max(8, Math.min(innerWidth - rect.right, innerWidth - 248)) })
        setOpen(true)
      }}>{trigger}</button>
    {mounted && position && createPortal(<div id={id} ref={menu} role="menu" aria-label={label} aria-hidden={exiting || undefined} inert={exiting}
      className={`wb-action-menu ${menuClassName} ${exiting ? 'wb-menu-exiting' : 'wb-menu-entering'}`}
      onAnimationEnd={event => { if (event.target === event.currentTarget && exiting) finishExit() }}
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
