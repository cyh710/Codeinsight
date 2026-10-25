import { useStore } from 'zustand'
import { layoutStore } from '../../store/layoutStore'

export default function SplitHandle({ side }: { side: 'left' | 'right' }) {
  const width = useStore(layoutStore, s => side === 'left' ? s.leftWidth : s.rightWidth)
  return <div role="separator" tabIndex={0} aria-label={`调整${side === 'left' ? '左' : '右'}栏宽度`} aria-orientation="vertical"
    aria-valuenow={width} aria-valuemin={side === 'left' ? 220 : 360} aria-valuemax={side === 'left' ? 360 : 720}
    aria-controls={side === 'left' ? 'workspace-left' : 'workspace-materials'} className="wb-split" title="拖动或用方向键调宽；双击恢复"
    onDoubleClick={() => layoutStore.getState().resize(side, side === 'left' ? 256 : 480)}
    onKeyDown={e => { if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); const delta = e.key === 'ArrowRight' ? 20 : -20; layoutStore.getState().resize(side, width + (side === 'left' ? delta : -delta)) } }}
    onPointerDown={e => { e.currentTarget.setPointerCapture(e.pointerId); e.currentTarget.dataset.drag = String(e.clientX); e.currentTarget.dataset.width = String(width) }}
    onPointerMove={e => { const start = e.currentTarget.dataset.drag; if (start !== undefined) { const delta = e.clientX - Number(start); layoutStore.getState().resize(side, Number(e.currentTarget.dataset.width) + (side === 'left' ? delta : -delta)) } }}
    onPointerUp={e => { delete e.currentTarget.dataset.drag }} onPointerCancel={e => { delete e.currentTarget.dataset.drag }} />
}
