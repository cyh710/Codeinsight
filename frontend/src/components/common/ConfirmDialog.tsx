import type { ReactNode } from 'react'
import Modal from './Modal'

interface ConfirmDialogProps {
  open: boolean
  title: string
  message: string | ReactNode
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
  /** Disable the confirm action while its async operation is in flight. */
  confirmBusy?: boolean
  /**
   * 层级覆盖。默认 z-[100]：确认框必须压过普通弹窗层（z-[90]，含设置/
   * 工作台宿主 z-[80]）；只有叠在其它确认框之上时才需要显式调高。
   */
  zClass?: string
  onConfirm: () => void
  onCancel: () => void
}

/**
 * 确认弹窗：Modal 的特化消费者。
 * 对外 API 与旧版一致，新增 ESC 关闭 / 遮罩淡入 / 焦点管理能力。
 * 危险操作用语义红（--color-danger），普通确认用天蓝主色。
 */
export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = '确认',
  cancelLabel = '取消',
  danger = false,
  confirmBusy = false,
  zClass = 'z-[100]',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <Modal open={open} onClose={onCancel} closeOnBackdrop={false} bare ariaLabel={title} zClass={zClass}>
      <div className="w-80 max-w-[90vw] rounded-lg border border-slate-200 bg-white p-5 shadow-2xl">
        <h3 className="mb-2 text-sm font-semibold text-slate-900">{title}</h3>
        <div className="mb-4 text-sm text-slate-600">{message}</div>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg px-4 py-1.5 text-xs text-slate-500 transition-colors hover:bg-slate-100"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={confirmBusy}
            className={`rounded-lg px-4 py-1.5 text-xs font-medium text-white transition-colors ${
              danger
                ? 'bg-red-600 hover:bg-red-700'
                : 'bg-accent hover:bg-accent-hover'
            } disabled:cursor-not-allowed disabled:opacity-45`}
          >
            {confirmBusy ? '处理中…' : confirmLabel}
          </button>
        </div>
      </div>
    </Modal>
  )
}
