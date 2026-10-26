import { useState } from 'react'
import { useStore } from 'zustand'
import { chatStore } from '../../store/chatStore'
import { projectStore } from '../../store/projectStore'
import { layoutStore } from '../../store/layoutStore'
import { Archive, Loader2, MoreHorizontal, Search, SlidersHorizontal, SquarePen, X } from 'lucide-react'
import ActionMenu from '../common/ActionMenu'
import { conversationGroups } from './conversationGroups'

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
  const [filtersOpen, setFiltersOpen] = useState<boolean | null>(null)
  const showFilters = filtersOpen ?? Boolean(state.search || state.allProjects || state.archived)
  const groups = conversationGroups(state.conversations)
  const open = async (pid: number, cid: string, request?: string) => {
    if (projectStore.getState().currentProjectId !== pid) await projectStore.getState().selectProject(pid)
    await chatStore.getState().openConversation(pid, cid, request)
    if (layoutStore.getState().viewport < 1280) layoutStore.setState({ left: false })
  }
  return <section aria-label="对话列表" className="sidebar-conversations flex min-h-0 flex-1 flex-col">
    <div className="sidebar-conversation-controls">
      <button type="button" className="sidebar-new-chat" disabled={state.projectId === null} onClick={() => { if (state.projectId !== null) void state.newConversation(state.projectId) }}><SquarePen size={17} />新建对话</button>
      <div className="sidebar-search-row"><div className="sidebar-search-field"><Search size={15} aria-hidden="true" /><input aria-label="搜索历史对话" placeholder="搜索对话…" value={state.search} onChange={e => state.searchConversations(e.target.value, state.allProjects, state.archived)} />{state.search && <button aria-label="清空对话搜索" onClick={() => state.searchConversations('', state.allProjects, state.archived)}><X size={14} /></button>}</div>
        <button className="wb-icon-button sidebar-filter-toggle" aria-label="对话筛选" aria-expanded={showFilters} data-active={state.allProjects || state.archived || undefined} onClick={() => setFiltersOpen(!showFilters)}><SlidersHorizontal size={16} /></button></div>
      {showFilters && <div className="sidebar-search-filters">
        <label><input type="checkbox" checked={state.allProjects} onChange={e => state.searchConversations(state.search, e.target.checked, state.archived)} /> 全部项目</label>
        <label><input type="checkbox" checked={state.archived} onChange={e => state.searchConversations(state.search, state.allProjects, e.target.checked)} /> 已归档</label>
      </div>}
    </div>
    <div className="sidebar-conversation-scroll min-h-0 flex-1 overflow-auto">
      {state.error && <p role="alert" className="p-2 text-xs text-danger">{state.error} <button onClick={() => void state.refreshConversations()}>重试</button></p>}
      {state.listLoading && <p role="status" className="sidebar-list-status"><Loader2 size={12} className="animate-spin" />更新对话列表…</p>}
      {!state.listLoading && !state.conversations.length && <p className="p-3 text-xs leading-6 text-slate-400">{state.search ? '没有找到匹配的对话。' : '还没有对话，点击上方开始。'}</p>}
      {groups.map(group => <section key={group.title} className="sidebar-conversation-group" aria-label={group.title}><h3>{state.archived && <Archive size={12} aria-hidden="true" />}{group.title}</h3>
      {group.items.map(c => <article key={`${c.project_id}:${c.id}`} data-conversation-id={c.id} data-status={c.status} className={`conversation-row sidebar-conversation-row ${c.id === state.conversationId && c.project_id === state.projectId ? 'active' : ''}`}>
        <div className="sidebar-conversation-main">
          <button className="sidebar-chat-open" title={c.title} type="button" onClick={() => void open(c.project_id, c.id, state.search ? c.match_request_id : undefined)}>
            <span className="sidebar-chat-title">{c.pinned && <span className="sidebar-pin" aria-label="已置顶">◆</span>}{c.title}</span>
            <span className="sidebar-chat-meta" title={updatedLabel(c.updated_at)}>{c.status === 'running' ? <><Loader2 size={11} className="animate-spin" />生成中</> : c.status === 'interrupted' ? '回答中断' : c.status === 'failed' ? '回答失败' : c.status === 'abstained' ? '待核实' : state.allProjects ? c.project_name : updatedLabel(c.updated_at)}{c.unread && c.status !== 'running' && <span className="sidebar-unread" aria-label="有新结果" />}</span>
            {state.search && c.snippet && <span className="conversation-preview">{preview(c.snippet)}</span>}
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
      </article>)}</section>)}
      {state.nextCursor !== null && <button className="wb-button w-full" onClick={() => void state.refreshConversations(true)}>加载更多对话</button>}
    </div>
  </section>
}
