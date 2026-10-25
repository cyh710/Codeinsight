import { useState } from 'react'
import { useStore } from 'zustand'
import { chatStore } from '../../store/chatStore'
import { projectStore } from '../../store/projectStore'
import { layoutStore } from '../../store/layoutStore'
import { MoreHorizontal, Plus } from 'lucide-react'
import ActionMenu from '../common/ActionMenu'

function updatedLabel(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' }) + ' ' + date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function preview(text: string): string {
  return text.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1').replace(/[#*`\n]+/g, ' ').trim()
}

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
    <div className="conversation-controls">
      <button type="button" className="wb-primary w-full" disabled={state.projectId === null} onClick={() => { if (state.projectId !== null) void state.newConversation(state.projectId) }}><Plus size={17} /> 新建对话</button>
      <input aria-label="搜索历史对话" placeholder="搜索标题或对话内容…" value={state.search} onChange={e => state.searchConversations(e.target.value, state.allProjects, state.archived)} className="wb-input w-full" />
      <div className="flex flex-wrap gap-3 text-xs text-slate-500">
        <label><input type="checkbox" checked={state.allProjects} onChange={e => state.searchConversations(state.search, e.target.checked, state.archived)} /> 全部项目</label>
        <label><input type="checkbox" checked={state.archived} onChange={e => state.searchConversations(state.search, state.allProjects, e.target.checked)} /> 已归档</label>
      </div>
    </div>
    <div className="min-h-0 flex-1 space-y-1 overflow-auto p-2">
      {state.error && <p role="alert" className="p-2 text-xs text-danger">{state.error} <button onClick={() => void state.refreshConversations()}>重试</button></p>}
      {state.listLoading && <p role="status" className="px-3 text-[10px] text-slate-400">更新对话列表…</p>}
      {!state.listLoading && !state.conversations.length && <p className="p-3 text-xs leading-6 text-slate-400">{state.search ? '没有找到匹配的对话。' : '还没有对话，点击上方开始。'}</p>}
      {state.conversations.map(c => <article key={`${c.project_id}:${c.id}`} data-conversation-id={c.id} className={`conversation-row ${c.id === state.conversationId && c.project_id === state.projectId ? 'active' : ''}`}>
        <div className="flex items-start gap-1">
          <button className="min-w-0 flex-1 text-left" title={c.title} type="button" onClick={() => void open(c.project_id, c.id, state.search ? c.match_request_id : undefined)}>
            <div className="truncate text-sm font-medium">{c.pinned ? '◆ ' : ''}{c.title}</div>
            <p className="conversation-meta">{state.allProjects ? `${c.project_name} · ` : ''}{c.status === 'running' ? '生成中' : c.status === 'interrupted' ? '回答中断' : c.status === 'failed' ? '回答失败' : c.status === 'abstained' ? '依据不足' : updatedLabel(c.updated_at)}{c.unread && c.status !== 'running' ? ' · 新结果' : ''}</p>
            {c.snippet && <p className="conversation-preview">{preview(c.snippet)}</p>}
          </button>
          <ActionMenu label={`对话操作 ${c.title}`} trigger={<MoreHorizontal size={17} />}>
            {close => <>
              <button role="menuitem" onClick={() => { close(); setRename(c.id); setTitle(c.title) }}>改名</button>
              <button role="menuitem" onClick={() => { void state.updateConversation(c.id, { pinned: !c.pinned }, c.project_id); close() }}>{c.pinned ? '取消置顶' : '置顶'}</button>
              <button role="menuitem" disabled={c.status === 'running'} onClick={() => { void state.updateConversation(c.id, { archived: !c.archived }, c.project_id); close() }}>{c.archived ? '恢复归档' : '归档'}</button>
            </>}
          </ActionMenu>
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
