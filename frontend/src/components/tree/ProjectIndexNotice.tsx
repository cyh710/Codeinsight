import { useEffect, useState } from 'react'
import { useStore } from 'zustand'
import { AlertCircle, CheckCircle2, LoaderCircle, X } from 'lucide-react'
import { projectStore } from '../../store/projectStore'
import { layoutStore } from '../../store/layoutStore'
import type { ProjectSummary } from '../../api/types'
import RelocateProjectDialog from './RelocateProjectDialog'

export default function ProjectIndexNotice() {
  const activities = useStore(projectStore, state => state.indexActivities)
  const current = useStore(projectStore, state => state.currentProjectId)
  const activity = (current === null ? undefined : activities[current])
    ?? Object.values(activities).sort((a, b) => b.observedAt - a.observedAt)[0]
  const [now, setNow] = useState(Date.now)
  const [repair, setRepair] = useState<ProjectSummary | null>(null)
  const active = activity?.phase === 'indexing' || activity?.phase === 'syncing'
  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [active])
  if (!activity) return null

  const { projectId, name, phase, detail, message } = activity
  const title = phase === 'indexing' ? `正在为 ${name} 建立索引`
    : phase === 'syncing' ? `${name} 索引已建立，正在加载文件`
    : phase === 'ready' ? `${name} 索引已就绪`
    : phase === 'failed' ? `${name} 索引未完成`
    : phase === 'paused' ? `${name} 索引仍在等待完成`
    : detail?.status === 'ready' || detail?.status === 'stale' ? `${name} 索引已建立，文件暂未加载`
    : `${name} 的索引状态暂不可读`
  const tone = active ? 'info' : phase === 'ready' ? 'success' : phase === 'failed' ? 'danger' : 'warning'
  const seconds = Math.max(0, Math.floor((now - activity.observedAt) / 1000))
  const wait = seconds < 60 ? `${seconds} 秒` : `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`
  const viewFiles = async () => {
    if (current !== projectId) await projectStore.getState().selectProject(projectId)
    layoutStore.setState({ sidebar: 'files', left: true, full: false })
  }

  return <>
    <section className={`index-notice index-notice--${tone}`} data-busy={active || undefined} aria-label="项目索引状态" data-testid="project-index-status">
      <div className="index-notice-icon" aria-hidden="true">
        {active ? <LoaderCircle size={19} className="motion-safe:animate-spin" /> : phase === 'ready' ? <CheckCircle2 size={19} /> : <AlertCircle size={19} />}
      </div>
      <div className="index-notice-body min-w-0 flex-1">
        <p className="text-sm font-medium" role={phase === 'failed' || phase === 'unavailable' ? 'alert' : 'status'}>{title}</p>
        <p className="mt-0.5 text-xs leading-5 text-slate-600">
          {active ? '可以继续浏览教材、写下问题或切换项目。'
            : phase === 'ready' && detail ? `${detail.files.toLocaleString()} 个文件 · ${detail.symbols.toLocaleString()} 个符号${message ? ` · ${message}` : ''}`
            : message || '请重新检查，或选择项目目录后重试。'}
          {active && <span className="ml-2 whitespace-nowrap text-slate-500" aria-hidden="true" title="从当前页面开始等待的时间">已等待 {wait}</span>}
        </p>
      </div>
      <div className="index-notice-actions">
        {current !== projectId && <button className="wb-button" onClick={() => void projectStore.getState().selectProject(projectId)}>返回项目</button>}
        {phase === 'ready' && <button className="wb-button" onClick={() => void viewFiles()}>查看文件</button>}
        {(phase === 'unavailable' || phase === 'paused') && <button className="wb-button" onClick={() => projectStore.getState().resumeIndexing(projectId)}>继续检查</button>}
        {phase === 'failed' && activity.request && <button className="wb-button" onClick={() => void projectStore.getState().retryIndexing(projectId)}>重试索引</button>}
        {phase === 'failed' && !activity.request && detail && <button className="wb-button" onClick={() => setRepair(detail)}>选择目录</button>}
        {!active && <button className="wb-icon-button" aria-label="关闭索引提示" onClick={() => projectStore.getState().dismissIndexActivity(projectId)}><X size={16} /></button>}
      </div>
    </section>
    {repair && <RelocateProjectDialog project={repair} onClose={() => setRepair(null)} />}
  </>
}
