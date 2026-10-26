import { useEffect, useState } from 'react'
import { useStore } from 'zustand'
import type { ExplorationState } from '../../api/types'
import { getConversation, patchConversation } from '../../api/conversations'
import { chatStore } from '../../store/chatStore'
import { projectStore } from '../../store/projectStore'

export default function ExplorationTrail() {
  const pid = useStore(projectStore, s => s.currentProjectId)
  const cid = useStore(chatStore, s => s.conversationId)
  const streaming = useStore(chatStore, s => s.streaming)
  const [state, setState] = useState<{ key: string; data: ExplorationState; error?: string }>()
  const [error, setError] = useState('')
  const key = `${pid}:${cid}`
  useEffect(() => {
    if (!pid || !cid || streaming) return
    let alive = true
    getConversation(pid, cid).then(meta => { if (alive) { setState({ key, data: meta.exploration_state ?? {} }); setError('') } })
      .catch(e => { if (alive) setError(String(e)) })
    return () => { alive = false }
  }, [pid, cid, key, streaming])
  const data = state?.key === key ? state.data : undefined
  if (!data?.current_question && !error) return null
  return <details className="exploration-trail"><summary>探索脉络{data?.stale ? ' · 来自旧索引' : ''}</summary>
    {error && <p role="alert">读取探索脉络失败：{error}</p>}
    {data && <><p className="exploration-muted">本会话已展示内容，不代表你已掌握。{data.stale ? '索引已更新，继续探索会重新核对代码。' : ''}</p>
      <p>{data.current_question}</p><ul>{data.items?.map((item, i) => <li key={`${item.request_id}:${i}`}><button type="button" onClick={() => void chatStore.getState().openConversation(pid!, cid, item.request_id)}>{item.text}</button></li>)}</ul>
      <button type="button" onClick={() => { void patchConversation(pid!, cid, { clear_exploration: true }).then(() => { setState({ key, data: {} }); setError('') }).catch(e => setError(String(e))) }}>清空脉络，保留对话</button>
    </>}
  </details>
}
