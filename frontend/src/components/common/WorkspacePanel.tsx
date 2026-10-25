import { type ReactNode } from 'react'
import { usePresence } from './Presence'

/** 退出完成后才收起空间；子树一直保留，避免动画清空阅读和草稿。 */
export default function WorkspacePanel({ id, side, open, overlay = false, children }: {
  id: string
  side: 'left' | 'right'
  open: boolean
  overlay?: boolean
  children: ReactNode
}) {
  const { mounted, exiting, finishExit } = usePresence(open, 300)
  return <div id={id}
    className={`${side === 'left' ? 'wb-left' : 'wb-materials'} wb-motion-panel ${overlay ? 'wb-overlay' : ''} ${!mounted ? 'wb-hidden' : ''}`}
    data-panel-state={open ? 'open' : exiting ? 'exiting' : 'closed'}
    aria-hidden={!open} inert={!open}
    onTransitionEnd={event => {
      if (event.target !== event.currentTarget || !exiting) return
      const changesWidth = getComputedStyle(event.currentTarget).transitionProperty.split(',').some(property => property.trim() === 'width')
      if (event.propertyName === 'width' || (event.propertyName === 'opacity' && !changesWidth)) finishExit()
    }}>
    <div className="wb-panel-surface">{children}</div>
  </div>
}
