import { useState } from 'react'
import { useStore } from 'zustand'
import { chatStore } from '../../store/chatStore'
import { projectStore } from '../../store/projectStore'
import { layoutStore } from '../../store/layoutStore'

export default function ConversationList() {
  const state = useStore(chatStore)
  const [rename, setRename] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const open = async (pid: number, cid: string, request?: string) => {
    if (projectStore.getState().currentProjectId !== pid) await projectStore.getState().selectProject(pid)
    await chatStore.getState().openConversation(pid, cid, request)
    if (layoutStore.getState().viewport < 1280) layoutStore.setState({ left: false })
  }
  return <section aria-label="对话列表" className="flex min-h-0 flex-1 flex-col">
    <div className="space-y-2 border-b border-slate-200/70 px-3 py-3">
      <button type="button" className="wb-primary w-full" disabled={state.projectId === null} onClick={() => { if (state.projectId !== null) void state.newConversation(state.projectId) }}>＋ 新建对话</button>
      <input aria-label="搜索历史对话" placeholder="搜索标题或对话内容…" value={state.search} onChange={e => state.searchConversations(e.target.value, state.allProjects, state.archived)} className="wb-input w-full" />
      <div className="flex flex-wrap gap-3 text-[11px] text-slate-500">
        <label><input type="checkbox" checked={state.allProjects} onChange={e => state.searchConversations(state.search, e.target.checked, state.archived)} /> 全部项目</label>
        <label><input type="checkbox" checked={state.archived} onChange={e => state.searchConversations(state.search, state.allProjects, e.target.checked)} /> 已归档</label>
      </div>
    </div>
    <div className="min-h-0 flex-1 space-y-1 overflow-auto p-2">
      {state.error && <p role="alert" className="p-2 text-xs text-danger">{state.error} <button onClick={() => void state.refreshConversations()}>重试</button></p>}
      {state.listLoading && <p role="status" className="px-3 text-[10px] text-slate-400">更新对话列表…</p>}
      {!state.listLoading && !state.conversations.length && <p className="p-3 text-xs leading-6 text-slate-400">{state.search ? '没有找到匹配的对话。' : '还没有对话，点击上方开始。'}</p>}
      {state.conversations.map(c => <article key={`${c.project_id}:${c.id}`} data-conversation-id={c.id} className={`conversation-row ${c.id === state.conversationId && c.project_id === state.projectId ? 'active' : ''}`}>
        <button className="w-full text-left" type="button" onClick={() => void open(c.project_id, c.id, state.search ? c.match_request_id : undefined)}>
          <div className="flex items-start gap-1.5"><span className="min-w-0 flex-1 truncate text-xs font-medium">{c.pinned ? '◆ ' : ''}{c.title}</span>{c.status === 'running' ? <span className="text-[10px] text-accent">生成中</span> : c.unread ? <span className="text-[10px] text-accent">新结果</span> : null}</div>
          <p className="mt-1 truncate text-[10px] text-slate-400">{state.allProjects ? `${c.project_name} · ` : ''}{c.status === 'interrupted' ? '回答中断' : c.status === 'failed' ? '回答失败' : c.status === 'abstained' ? '依据不足' : '探索记录'}</p>
          {state.search && c.snippet && <p className="mt-1 line-clamp-2 text-[11px] leading-5 text-slate-500">{c.snippet}</p>}
        </button>
        <div className="mt-1 flex flex-wrap gap-2 text-[10px] text-slate-400">
          <button type="button" onClick={() => { setRename(c.id); setTitle(c.title) }}>改名</button>
          <button type="button" onClick={() => void state.updateConversation(c.id, { pinned: !c.pinned }, c.project_id)}>{c.pinned ? '取消置顶' : '置顶'}</button>
          <button type="button" disabled={c.status === 'running'} onClick={() => void state.updateConversation(c.id, { archived: !c.archived }, c.project_id)}>{c.archived ? '恢复归档' : '归档'}</button>
        </div>
        {rename === c.id && <form className="mt-2 flex gap-1" onSubmit={e => { e.preventDefault(); void state.updateConversation(c.id, { title }, c.project_id); setRename(null) }}>
          <input aria-label="对话名称" className="wb-input min-w-0 flex-1" value={title} onChange={e => setTitle(e.target.value)} maxLength={120} autoFocus />
          <button type="submit" disabled={!title.trim()} className="text-xs text-accent">保存</button><button type="button" className="text-xs" onClick={() => setRename(null)}>取消</button>
        </form>}
      </article>)}
      {state.nextCursor !== null && <button className="wb-button w-full" onClick={() => void state.refreshConversations(true)}>加载更多对话</button>}
    </div>
  </section>
}
