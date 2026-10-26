import { useState } from 'react'
import { Copy, FolderSearch, MoreHorizontal, Trash2 } from 'lucide-react'
import type { ProjectSummary } from '../../api/types'
import { ApiError } from '../../api/client'
import { projectStore } from '../../store/projectStore'
import ActionMenu from '../common/ActionMenu'
import Modal from '../common/Modal'

/** 移除操作只针对当前项目身份；确认框明确数据范围，不触碰源码。 */
export default function ProjectActions({ project, onRelocate }: { project: ProjectSummary; onRelocate: () => void }) {
  const [open, setOpen] = useState(false)
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const close = () => { if (!busy) { setOpen(false); setConfirmed(false); setError('') } }
  return <>
    <ActionMenu label="项目操作" menuClassName="sidebar-project-menu" trigger={<MoreHorizontal size={18} />}>
      {dismiss => <>
        <div className="wb-menu-caption">{project.name}</div>
        <p className="sidebar-menu-path">{project.root_path}</p>
        <button role="menuitem" onClick={() => { setError(''); void navigator.clipboard.writeText(project.root_path).then(() => setCopied(true), () => { setCopied(false); setError('复制失败，请重试') }) }}><Copy size={15} />{copied ? '已复制路径' : error && !open ? error : '复制项目路径'}</button>
        <button role="menuitem" onClick={() => { dismiss(); onRelocate() }}><FolderSearch size={15} />重新定位源码</button>
        <div className="sidebar-menu-separator" />
        <button role="menuitem" className="sidebar-danger" onClick={() => { dismiss(); setOpen(true); setError('') }}><Trash2 size={15} />移除项目…</button>
      </>}
    </ActionMenu>
    <Modal open={open} onClose={close} closeOnBackdrop={false} bare ariaLabel="移除项目">
      <div className="sidebar-remove-dialog">
        <div className="sidebar-remove-icon"><Trash2 size={21} /></div>
        <h2>移除项目</h2><p className="sidebar-remove-name">{project.name}</p>
        <p>将清除这个项目在 CodeInsight 中的索引、全部对话及阅读记录。</p>
        <p className="sidebar-source-kept">磁盘上的源码文件和内置教材会保留。</p>
        <p className="sidebar-remove-path" title={project.root_path}>{project.root_path}</p>
        <label className="sidebar-remove-check"><input type="checkbox" checked={confirmed} disabled={busy} onChange={e => setConfirmed(e.target.checked)} />我确认清除该项目的索引和全部对话</label>
        {error && <p role="alert" className="sidebar-danger">{error}</p>}
        <div className="sidebar-remove-buttons"><button className="wb-button" onClick={close} disabled={busy}>取消</button>
          <button className="sidebar-remove-confirm" disabled={!confirmed || busy} onClick={() => {
            setBusy(true); setError('')
            void projectStore.getState().removeProject(project.id).then(() => setOpen(false))
              .catch(e => setError(e instanceof ApiError ? `${e.title}。${e.hint}` : e instanceof Error ? e.message : String(e))).finally(() => setBusy(false))
          }}>{busy ? '正在移除…' : '确认移除'}</button></div>
      </div>
    </Modal>
  </>
}
