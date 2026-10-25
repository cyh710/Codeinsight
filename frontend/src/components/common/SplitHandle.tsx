import { useRef } from 'react'
import { useStore } from 'zustand'
import { layoutStore } from '../../store/layoutStore'

interface Drag {
  x: number
  width: number
  visible: boolean
  full: boolean
  single: boolean
  storedWidth: number
  originalOpen: boolean
}

export default function SplitHandle({ side, overlay = false }: {
  side: 'left' | 'right'
  overlay?: boolean
}) {
  const layout = useStore(layoutStore)
  const drag = useRef<Drag | null>(null)
  const width = side === 'left' ? layout.leftWidth : layout.rightWidth
  const visible = side === 'left' ? layout.left && !layout.full : layout.right
  const name = side === 'left' ? '左' : '右'
  const restore = () => {
    layoutStore.setState(side === 'left'
      ? { left: true, full: false }
      : { right: true, full: false })
  }
  const classes = ['wb-split', !visible ? `wb-edge wb-edge-${side}` : '',
    visible && overlay ? `wb-split-overlay wb-split-overlay-${side}` : ''].filter(Boolean).join(' ')

  return <div role="separator" tabIndex={0}
    aria-label={visible ? `调整${name}栏宽度` : `拖动打开${name}栏`}
    aria-orientation="vertical" aria-valuenow={visible ? width : 0} aria-valuemin={0}
    aria-valuemax={side === 'left' ? 360 : 720}
    aria-controls={side === 'left' ? 'workspace-left' : 'workspace-materials'}
    className={classes}
    title={visible ? '拖向边缘收起，向内拖动调宽；双击恢复默认宽度' : '向内拖动展开；按 Enter 恢复'}
    onDoubleClick={() => {
      restore()
      layoutStore.getState().resize(side, side === 'left' ? 256 : 480)
    }}
    onKeyDown={event => {
      const inward = side === 'left' ? 'ArrowRight' : 'ArrowLeft'
      const outward = side === 'left' ? 'ArrowLeft' : 'ArrowRight'
      if (event.key === 'Enter' && !visible) {
        event.preventDefault(); restore()
      } else if (event.key === 'Home' || (event.key === outward && width <= (side === 'left' ? 220 : 360))) {
        event.preventDefault(); layoutStore.getState().dragSidebar(side, 0, false)
      } else if (event.key === inward || event.key === outward) {
        event.preventDefault()
        if (!visible) { if (event.key === inward) restore() }
        else layoutStore.getState().resize(side, width + (event.key === inward ? 20 : -20))
      }
    }}
    onPointerDown={event => {
      if (event.button !== 0) return
      event.preventDefault()
      const panel = document.getElementById(side === 'left' ? 'workspace-left' : 'workspace-materials')
      drag.current = { x: event.clientX, width: visible ? panel?.getBoundingClientRect().width ?? width : 0,
        visible, full: layout.full, single: side === 'right' && (layout.full || layout.viewport < 1100), storedWidth: width,
        originalOpen: side === 'left' ? layout.left : layout.right }
      event.currentTarget.setPointerCapture(event.pointerId)
    }}
    onPointerMove={event => {
      const start = drag.current
      if (!start) return
      const inward = (event.clientX - start.x) * (side === 'left' ? 1 : -1)
      if (Math.abs(inward) < 4) return
      if (start.single && start.visible) {
        // 单区阅读没有并排宽度，用向外拖动返回原工作区。
        layoutStore.setState({ right: inward > -80, full: inward > -80 && start.full })
      } else layoutStore.getState().dragSidebar(side, start.width + inward, !start.visible)
    }}
    onPointerUp={() => { drag.current = null }}
    onPointerCancel={() => {
      const start = drag.current
      drag.current = null
      if (!start) return
      layoutStore.setState(side === 'left'
        ? { left: start.originalOpen, leftWidth: start.storedWidth, full: start.full }
        : { right: start.originalOpen, rightWidth: start.storedWidth, full: start.full })
    }}
    onLostPointerCapture={() => { drag.current = null }}
  />
}
