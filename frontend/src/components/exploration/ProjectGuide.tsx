import { useEffect, useState } from 'react'
import { useStore } from 'zustand'
import { api } from '../../api/dataSource'
import type { ProjectOverview } from '../../api/types'
import { projectStore } from '../../store/projectStore'
import { workbenchStore } from '../../store/workbenchStore'
import ExplorationActions from './ExplorationActions'
import { openCode } from './actions'

export default function ProjectGuide() {
  const pid = useStore(projectStore, s => s.currentProjectId)
  const detail = useStore(projectStore, s => s.currentDetail)
  const [result, setResult] = useState<{ pid: number; epoch: number; data?: ProjectOverview; error?: string }>()
  const [retry, setRetry] = useState(0)
  const epoch = detail?.index_epoch ?? 0
  useEffect(() => {
    if (pid === null) return
    let alive = true
    api.getProjectOverview(pid).then(data => { if (alive) setResult({ pid, epoch, data }) })
      .catch(error => { if (alive) setResult({ pid, epoch, error: String(error) }) })
    return () => { alive = false }
  }, [pid, epoch, retry])
  const state = result?.pid === pid && result.epoch === epoch ? result : undefined
  const data = state?.data
  return <section className="project-guide" aria-label="项目导览">
    <h2>{detail?.name ?? '从一个问题开始'}</h2>
    {pid === null ? <p>先在左侧选择或导入项目，也可以打开教材了解基础知识。</p> : !state ? <p role="status">读取已索引的项目入口…</p> : state.error ? <p role="alert">项目导览读取失败。<button type="button" onClick={() => setRetry(n => n + 1)}>重新读取</button></p> : <>
      {data?.project_intro ? <div className="project-guide-intro"><p>{data.project_intro.text}</p><button type="button" onClick={() => openCode(data.project_intro!.source)}>项目说明摘录 · {data.project_intro.source.path}:{data.project_intro.source.lineno}</button></div> : <p className="exploration-muted">尚未从索引中找到可引用的项目说明，可以从下面的实际对象开始。</p>}
      {detail?.status === 'indexing' && <p role="status">项目代码正在准备；入口仍对应上一次完成的索引。</p>}
      {detail?.source_available === false && <p role="status">源码目录不可用，仍可查看已保存的证据、对话和教材。</p>}
      {data?.exploration_entries?.length ? <ExplorationActions actions={data.exploration_entries}
        version={{ project_id: pid, head_commit: data.head_commit ?? null, index_epoch: data.index_epoch ?? 0 }} overview /> : <p className="exploration-muted">当前没有足够证据生成探索入口。可以先查看文件或直接提问；尚未索引时请等待索引完成。</p>}
    </>}
    <div className="project-guide-footer"><button type="button" onClick={() => workbenchStore.getState().openKnowledgeTree()}>浏览完整教材</button></div>
  </section>
}
