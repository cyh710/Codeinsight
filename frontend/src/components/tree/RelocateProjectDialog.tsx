import { useState } from 'react'
import { FolderOpen, LoaderCircle } from 'lucide-react'
import { ApiError } from '../../api/client'
import { selectProjectFolder } from '../../api/projects'
import type { ProjectSummary } from '../../api/types'
import { projectStore } from '../../store/projectStore'
import Button from '../common/Button'
import Modal from '../common/Modal'

export default function RelocateProjectDialog({ project, onClose }: {
  project: ProjectSummary
  onClose: () => void
}) {
  const [rootPath, setRootPath] = useState('')
  const [picking, setPicking] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const busy = picking || submitting

  const selectFolder = async () => {
    setPicking(true); setError('')
    try {
      const selection = await selectProjectFolder()
      if (selection.root_path) setRootPath(selection.root_path)
    } catch (failure) {
      setError(failure instanceof ApiError ? `${failure.title}。${failure.hint}` : '文件夹选择失败，请重试。')
    } finally { setPicking(false) }
  }

  const submit = async () => {
    setSubmitting(true); setError('')
    const accepted = await projectStore.getState().relocateProject(project.id, rootPath)
    if (accepted) onClose()
    else setError(projectStore.getState().importError || '提交失败，请重试。')
    setSubmitting(false)
  }

  return <Modal open title="重新定位源码目录" onClose={() => { if (!busy) onClose() }} widthClass="max-w-lg" closeOnBackdrop={false}>
    <div className="space-y-4">
      <div>
        <p className="text-sm text-slate-700">为 <strong>{project.name}</strong> 选择现在的 Git 项目文件夹。</p>
        <p className="mt-1 text-xs leading-5 text-slate-500">将重建索引，保留对话和工作记录。失败时保留原索引。</p>
      </div>
      <div className="space-y-1 text-xs">
        <p className="text-slate-500">原目录</p>
        <p className="break-all text-slate-600">{project.root_path}</p>
      </div>
      <div className="rounded-lg bg-slate-50 p-3">
        <p className="mb-3 break-all text-sm text-slate-700" aria-live="polite">{rootPath || '尚未选择新目录'}</p>
        <Button size="sm" onClick={() => void selectFolder()} disabled={busy} autoFocus>
          {picking ? <LoaderCircle size={14} className="animate-spin" /> : <FolderOpen size={14} />}
          {picking ? '等待选择…' : rootPath ? '更换文件夹' : '选择文件夹'}
        </Button>
        {picking && <p role="status" className="mt-2 text-xs text-slate-500">请在系统窗口中选择文件夹，或取消返回。</p>}
      </div>
      {error && <p role="alert" className="text-sm leading-5 text-danger">{error}</p>}
      <div className="flex justify-end gap-2">
        <Button size="sm" disabled={busy} onClick={onClose}>取消</Button>
        <Button size="sm" variant="primary" disabled={busy || !rootPath} onClick={() => void submit()}>
          {submitting ? '提交中…' : '重新关联并重建索引'}
        </Button>
      </div>
    </div>
  </Modal>
}
