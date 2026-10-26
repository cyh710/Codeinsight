/**
 * 对话窗口：消息列表 + 输入框。滚动吸底抄织忆 ChatWindow 的手法
 * （`wasAtBottomRef` 记住用户是否在底部，只在底部时自动跟随新内容——
 * 用户正往上翻历史时不许拽他下来）。
 */
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useStore } from 'zustand'
import { chatStore } from '../../store/chatStore'
import type { Citation } from '../../api/types'
import MessageBubble from './MessageBubble'
import InputBox from './InputBox'
import { workbenchStore } from '../../store/workbenchStore'
import { ArrowDown, ArrowUp, Search, X } from 'lucide-react'
import ProjectGuide from '../exploration/ProjectGuide'
import ExplorationTrail from '../exploration/ExplorationTrail'

export default function ChatWindow({ onOpenCitation }: { onOpenCitation: (c: Citation) => void }) {
  const messages = useStore(chatStore, (s) => s.messages)
  const conversationId = useStore(chatStore, (s) => s.conversationId)
  const find = useStore(chatStore, (s) => s.find)
  const focus = useStore(chatStore, (s) => s.focusRequest)
  const cursor = useStore(chatStore, (s) => s.turnsCursor)
  const loading = useStore(chatStore, (s) => s.loading)
  const error = useStore(chatStore, (s) => s.error)
  const archived = useStore(chatStore, s => s.currentArchived)
  const saved = useStore(workbenchStore, (s) => s.chatScroll)
  const scrollRef = useRef<HTMLDivElement>(null)
  const anchorRef = useRef<HTMLDivElement>(null)
  const wasAtBottomRef = useRef(true)
  const [searchOpen, setSearchOpen] = useState(false)
  const [guideOpen, setGuideOpen] = useState(false)
  const [matchIndex, setMatchIndex] = useState(0)
  const title = useStore(chatStore, s => s.currentTitle)
  const matches = messages.filter(m => find && m.text.toLowerCase().includes(find.toLowerCase()))
  const locate = (direction: number) => {
    if (!matches.length) return
    const next = (matchIndex + direction + matches.length) % matches.length
    setMatchIndex(next)
    document.getElementById(`message-${matches[next].id}`)?.scrollIntoView({ block: 'center' })
  }
  useLayoutEffect(() => {
    const el = scrollRef.current
    if (el && saved !== null) el.scrollTop = saved
    wasAtBottomRef.current = saved === null || Boolean(el && el.scrollHeight - el.scrollTop - el.clientHeight < 48)
  }, [conversationId, loading]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (focus && !loading) document.getElementById(`message-user-${focus}`)?.scrollIntoView({ block: 'center' })
  }, [focus, loading])

  // 流式增量到来时吸底；用户翻离底部则停止跟随。
  useLayoutEffect(() => {
    if (loading || !wasAtBottomRef.current) return
    anchorRef.current?.scrollIntoView({ block: 'end' })
  }, [messages, loading])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const onScroll = () => {
      if (chatStore.getState().loading) return
      wasAtBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48
      workbenchStore.getState().setChatScroll(el.scrollTop)
    }
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <section className="flex h-full min-h-0 min-w-0 flex-1 flex-col bg-bg">
      <div className="chat-toolbar">
        {searchOpen ? <>
          <Search size={16} className="shrink-0 text-slate-400" />
          <input autoFocus aria-label="查找当前对话" placeholder="查找已加载消息…" value={find} onChange={e => {
            chatStore.getState().setFind(e.target.value); setMatchIndex(0)
            const first = e.target.value && messages.find(m => m.text.toLowerCase().includes(e.target.value.toLowerCase()))
            if (first) requestAnimationFrame(() => document.getElementById(`message-${first.id}`)?.scrollIntoView({ block: 'center' }))
          }} className="min-w-0 flex-1 bg-transparent text-sm outline-none"
            onKeyDown={e => { if (e.key === 'Enter') locate(e.shiftKey ? -1 : 1); if (e.key === 'Escape') { setSearchOpen(false); chatStore.getState().setFind('') } }} />
          {find && <span className="whitespace-nowrap text-xs text-slate-500">{matches.length ? `${matchIndex % matches.length + 1}/` : ''}{matches.length} 条</span>}
          <button className="wb-icon-button" aria-label="上一条匹配消息" disabled={!matches.length} onClick={() => locate(-1)}><ArrowUp size={15} /></button>
          <button className="wb-icon-button" aria-label="下一条匹配消息" disabled={!matches.length} onClick={() => locate(1)}><ArrowDown size={15} /></button>
          <button className="wb-icon-button" aria-label="关闭对话查找" onClick={() => { setSearchOpen(false); chatStore.getState().setFind('') }}><X size={16} /></button>
        </> : <><h2 className="min-w-0 flex-1 truncate text-sm font-medium text-slate-600">{title}</h2><button className="wb-button" aria-expanded={guideOpen} onClick={() => setGuideOpen(v => !v)}>项目导览</button><button className="wb-icon-button" aria-label="查找当前对话" title="查找当前对话" onClick={() => setSearchOpen(true)}><Search size={17} /></button></>}
      </div>
      {searchOpen && cursor !== null && <p className="px-5 pb-2 text-xs text-slate-500">仅查找已加载消息。<button className="text-accent" onClick={() => void chatStore.getState().loadMore()}>加载更早记录</button></p>}
      {error && <p role="alert" className="px-4 py-2 text-xs text-danger">{error} <button type="button" onClick={() => void chatStore.getState().openConversation(chatStore.getState().projectId!, conversationId)}>重新读取</button></p>}
      {archived && <p className="px-4 py-2 text-xs text-slate-500">这份对话已归档；继续提问会恢复到当前项目列表。</p>}
      <div ref={scrollRef} data-chat-scroll className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <div className="mx-auto flex max-w-3xl flex-col gap-3">
          {loading && <p role="status" className="text-xs text-slate-500">读取对话与阅读工作区…</p>}
          {cursor !== null && <button type="button" className="text-xs text-accent" onClick={() => void chatStore.getState().loadMore()}>加载更早的对话</button>}
          {!loading && (messages.length === 0 || guideOpen) && <ProjectGuide />}
          {!loading && <ExplorationTrail />}
          {messages.map((m) => (
            <div key={m.id} id={`message-${m.id}`} data-match={Boolean(find && m.text.toLowerCase().includes(find.toLowerCase()))} className={find && m.text.toLowerCase().includes(find.toLowerCase()) ? 'rounded-xl ring-2 ring-amber-300' : ''}>
              <MessageBubble message={m} onOpenCitation={onOpenCitation} />
            </div>
          ))}
          <div ref={anchorRef} />
        </div>
      </div>
      <InputBox />
    </section>
  )
}
