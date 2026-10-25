/**
 * 导入项目对话框（POST /projects，契约 §3.3）：本地仓库绝对路径 + 可选
 * 名称与 git ref。提交后 202 返回，状态由左栏的状态行接管（轮询）。
 * 失败在对话框内联显示（契约错误形状的 title/hint），不弹 Toast——
 * 用户改一下输入就能重试，上下文不该被打断。
 */
import { useState } from 'react'
import { useStore } from 'zustand'
import { AlertTriangle, FolderInput } from 'lucide-react'
import { isMockMode } from '../../api/dataSource'
import { projectStore } from '../../store/projectStore'
import Modal from '../common/Modal'
import Button from '../common/Button'

export default function ImportProjectDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const importing = useStore(projectStore, (s) => s.importing)
  const importError = useStore(projectStore, (s) => s.importError)
  const [rootPath, setRootPath] = useState('')
  const [name, setName] = useState('')
  const [ref, setRef] = useState('')

  const submit = async () => {
    if (!rootPath.trim()) return
    await projectStore.getState().importProject(rootPath.trim(), name.trim() || undefined, ref.trim() || undefined)
    // 成功（开始轮询）即关对话框：状态交给左栏状态行；
    // 失败（importError 非空）留在对话框里让用户改了再试。
    if (!projectStore.getState().importError) onClose()
  }

  const inputCls =
    'w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 outline-none transition-colors focus:border-accent'

  return (
    <Modal open={open} onClose={onClose} title="导入项目并建索引" widthClass="max-w-md" closeOnBackdrop={false}>
      <div className="space-y-3">
        <p className="text-[11px] leading-relaxed text-slate-500">
          选择一个本地 Git 仓库的绝对路径。索引会在后台建立，
          提交后左栏会显示进度状态，完成后文件树自动刷新。
        </p>
        <label className="block">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            仓库路径（必填）
          </span>
          <input
            className={`mt-1 ${inputCls} font-mono`}
            placeholder="/path/to/some-repo"
            value={rootPath}
            onChange={(e) => setRootPath(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.nativeEvent.isComposing) void submit()
            }}
            autoFocus
          />
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              显示名（可选）
            </span>
            <input
              className={`mt-1 ${inputCls}`}
              placeholder="缺省 = 目录名"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              git ref（可选）
            </span>
            <input
              className={`mt-1 ${inputCls} font-mono`}
              placeholder="缺省 = 当前 HEAD"
              value={ref}
              onChange={(e) => setRef(e.target.value)}
            />
          </label>
        </div>

        {isMockMode && (
          <p className="rounded-lg bg-warning/10 px-2.5 py-1.5 text-[11px] leading-relaxed text-warning">
            当前是 mock 快照模式：导入会明确报错。要真实导入，设
            <code className="mx-1 rounded bg-white/60 px-1 font-mono">VITE_CI_MOCK=0</code>
            并启动后端（8020）。
          </p>
        )}

        {importError && (
          <p className="flex items-start gap-1.5 rounded-lg bg-danger-soft/50 px-2.5 py-1.5 text-[11px] leading-relaxed text-danger" role="alert">
            <AlertTriangle size={13} strokeWidth={1.7} className="mt-px shrink-0" />
            {importError}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" size="sm" onClick={onClose} disabled={importing}>
            取消
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => void submit()}
            disabled={!rootPath.trim() || importing}
          >
            <FolderInput size={13} strokeWidth={1.8} />
            {importing ? '提交中…' : '导入并建索引'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
