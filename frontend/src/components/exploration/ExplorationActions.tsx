import { useStore } from 'zustand'
import type { ActionOrigin, ExplorationAction, ExplorationResult } from '../../api/types'
import { chatStore } from '../../store/chatStore'
import { projectStore } from '../../store/projectStore'
import { viewStore } from '../../store/viewStore'
import { layoutStore } from '../../store/layoutStore'
import { knowledgeTarget, openCode, openRelated } from './actions'

export default function ExplorationActions({ actions, version, requestId, overview = false }: {
  actions: ExplorationAction[]
  version: Pick<ExplorationResult, 'project_id' | 'head_commit' | 'index_epoch'>
  requestId?: string
  overview?: boolean
}) {
  const streaming = useStore(chatStore, s => s.streaming)
  const loading = useStore(chatStore, s => s.loading)
  const cid = useStore(chatStore, s => s.conversationId)
  const detail = useStore(projectStore, s => s.currentDetail)
  const pid = useStore(projectStore, s => s.currentProjectId)
  const stale = pid !== version.project_id || Boolean(detail && (detail.index_epoch !== version.index_epoch || detail.head_commit !== version.head_commit))
  const activate = (action: ExplorationAction) => {
    if (stale) return
    if (action.kind === 'follow_up') {
      const origin: ActionOrigin = { kind: overview ? 'overview' : 'answer', action_id: action.id, index_epoch: version.index_epoch, ...(requestId ? { request_id: requestId } : {}) }
      viewStore.getState().setCenterTab('chat')
      layoutStore.setState({ full: false, ...(layoutStore.getState().viewport < 1100 ? { right: false } : {}) })
      void chatStore.getState().sendMessage(version.project_id, action.question, { preserveDraft: true, reading: action.target, origin })
    } else if (action.kind === 'code' && action.target?.kind === 'code') openCode(action.target)
    else if (action.kind === 'knowledge' && action.target) {
      const target = knowledgeTarget(action.target)
      if (target) openRelated(target, version.project_id, cid, requestId)
    } else if (action.kind === 'graph' && action.target?.kind === 'code') { layoutStore.setState({ full: false, ...(layoutStore.getState().viewport < 1100 ? { right: false } : {}) }); viewStore.getState().openGraph(action.target.qualname) }
    else if (action.kind === 'timeline') { layoutStore.setState({ full: false, ...(layoutStore.getState().viewport < 1100 ? { right: false } : {}) }); viewStore.getState().openTimeline() }
  }
  if (!actions.length) return null
  return <nav className={overview ? 'project-exploration-entries' : 'exploration-actions'} aria-label={overview ? '项目探索入口' : '接着探索'}>
    {!overview && <p className="exploration-section-label">接着探索</p>}
    {stale && <p role="status" className="exploration-muted">入口来自旧索引，请刷新项目导览；历史正文仍可阅读。</p>}
    {actions.slice(0, overview ? 4 : 3).map(action => <button key={action.id} type="button"
      disabled={stale || loading || (action.kind === 'follow_up' && streaming)} onClick={() => activate(action)}>
      <span className="exploration-action-kind">{{ follow_up: '追问', code: '代码', knowledge: '理解', graph: '关系', timeline: '变更' }[action.kind]}</span>
      <span><strong>{action.label}</strong>{action.reason && <small>{action.reason}</small>}</span>
      <span aria-hidden="true">↗</span>
    </button>)}
  </nav>
}
