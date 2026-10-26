/**
 * 导入项目对话框（POST /projects，契约 §3.3）：选择本地仓库文件夹 + 可选
 * 名称与 git ref。提交后 202 返回，状态由左栏的状态行接管（轮询）。
 * 失败在对话框内联显示（契约错误形状的 title/hint），不弹 Toast——
 * 用户改一下输入就能重试，上下文不该被打断。
 */
import { useState } from 'react'
import { useStore } from 'zustand'
import { AlertTriangle, FolderInput, FolderOpen, LoaderCircle } from 'lucide-react'
import { ApiError } from '../../api/client'
import { selectProjectFolder } from '../../api/projects'
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
  const [picking, setPicking] = useState(false)
  const [pickerError, setPickerError] = useState('')

  const selectFolder = async () => {
    setPicking(true)
    setPickerError('')
    projectStore.setState({ importError: '' })
    try {
      const selected = await selectProjectFolder()
      if (selected.root_path) setRootPath(selected.root_path)
    } catch (error) {
      setPickerError(error instanceof ApiError
        ? error.status === 404
          ? '文件夹选择服务尚未加载，请重启 CodeInsight 后端后重试。'
          : `${error.title}。${error.hint}`
        : '文件夹选择失败，请重试。')
    } finally { setPicking(false) }
  }

  const submit = async () => {
    if (!rootPath.trim()) return
    setPickerError('')
    await projectStore.getState().importProject(rootPath.trim(), name.trim() || undefined, ref.trim() || undefined)
    // 成功（开始轮询）即关对话框：状态交给左栏状态行；
    // 失败（importError 非空）留在对话框里让用户改了再试。
    if (!projectStore.getState().importError) onClose()
  }

  const inputCls =
    'w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 outline-none transition-colors focus:border-accent'

  return (
    <Modal open={open} onClose={() => { if (!picking && !importing) onClose() }} title="导入项目并建索引" widthClass="max-w-md" closeOnBackdrop={false}>
      <div className="space-y-3" aria-busy={importing}>
        <p className="text-[11px] leading-relaxed text-slate-500">
          选择 Git 项目文件夹，索引将在后台建立。
        </p>
        <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-medium text-slate-700">
            <FolderOpen size={16} className="shrink-0 text-sky-600" />
            {rootPath ? '已选项目文件夹' : '项目文件夹'}
          </div>
          <p className="mb-3 break-all text-xs leading-5 text-slate-500" aria-live="polite">
            {rootPath || '尚未选择文件夹'}
          </p>
          <Button variant="secondary" size="sm" onClick={() => void selectFolder()}
            disabled={picking || importing || isMockMode}
            autoFocus
          >
            {picking ? <LoaderCircle size={14} className="animate-spin" /> : <FolderOpen size={14} />}
            {picking ? '等待选择…' : rootPath ? '更换文件夹' : '选择文件夹'}
          </Button>
          {picking && <p role="status" className="mt-2 text-[11px] text-slate-500">请在系统窗口中选择文件夹，或取消返回。</p>}
        </div>
        <details className="import-options"><summary>更多选项</summary><div className="mt-3 grid grid-cols-2 gap-2">
          <label className="block">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              显示名（可选）
            </span>
            <input
              className={`mt-1 ${inputCls}`}
              placeholder="缺省 = 目录名"
              value={name}
              disabled={importing || picking}
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
              disabled={importing || picking}
              onChange={(e) => setRef(e.target.value)}
            />
          </label>
        </div></details>

        {isMockMode && (
          <p className="rounded-lg bg-warning/10 px-2.5 py-1.5 text-[11px] leading-relaxed text-warning">
            当前是 mock 快照模式：导入会明确报错。要真实导入，设
            <code className="mx-1 rounded bg-white/60 px-1 font-mono">VITE_CI_MOCK=0</code>
            并启动后端（8020）。
          </p>
        )}

        {(pickerError || importError) && (
          <p className="flex items-start gap-1.5 rounded-lg bg-danger-soft/50 px-2.5 py-1.5 text-[11px] leading-relaxed text-danger" role="alert">
            <AlertTriangle size={13} strokeWidth={1.7} className="mt-px shrink-0" />
            {pickerError || importError}
          </p>
        )}
        {importing && <p role="status" className="text-xs leading-5 text-accent">正在提交导入请求，接受后将在工作台显示索引状态。</p>}

        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" size="sm" onClick={onClose} disabled={importing || picking}>
            取消
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => void submit()}
            disabled={!rootPath.trim() || importing || picking}
          >
            {importing ? <LoaderCircle size={14} className="motion-safe:animate-spin" /> : <FolderInput size={13} strokeWidth={1.8} />}
            {importing ? '提交中…' : '导入并建索引'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
