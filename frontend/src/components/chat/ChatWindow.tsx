/**
 * 对话窗口：消息列表 + 输入框。滚动吸底抄织忆 ChatWindow 的手法
 * （`wasAtBottomRef` 记住用户是否在底部，只在底部时自动跟随新内容——
 * 用户正往上翻历史时不许拽他下来）。
 */
import { useEffect, useLayoutEffect, useRef } from 'react'
import { useStore } from 'zustand'
import { chatStore } from '../../store/chatStore'
import type { Citation } from '../../api/types'
import MessageBubble from './MessageBubble'
import InputBox from './InputBox'
import { workbenchStore } from '../../store/workbenchStore'

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
      <div className="chat-toolbar flex items-center gap-2 border-b border-slate-200/60 px-4 py-2">
        <input aria-label="查找当前对话" placeholder="查找当前对话…" value={find} onChange={e => chatStore.getState().setFind(e.target.value)} className="min-w-0 flex-1 rounded border border-slate-200 bg-white px-2 py-1 text-xs" />
        {find && <span className="text-xs text-slate-500">{messages.filter(m => m.text.toLowerCase().includes(find.toLowerCase())).length} 处</span>}
        {find && <button type="button" className="text-xs text-accent" onClick={() => scrollRef.current?.querySelector('[data-match="true"]')?.scrollIntoView({ block: 'center' })}>定位首处</button>}
      </div>
      {error && <p role="alert" className="px-4 py-2 text-xs text-danger">{error} <button type="button" onClick={() => void chatStore.getState().openConversation(chatStore.getState().projectId!, conversationId)}>重新读取</button></p>}
      {archived && <p className="px-4 py-2 text-xs text-slate-500">这份对话已归档；继续提问会恢复到当前项目列表。</p>}
      <div ref={scrollRef} data-chat-scroll className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <div className="mx-auto flex max-w-3xl flex-col gap-3">
          {loading && <p role="status" className="text-xs text-slate-500">读取对话与阅读工作区…</p>}
          {cursor !== null && <button type="button" className="text-xs text-accent" onClick={() => void chatStore.getState().loadMore()}>加载更早的对话</button>}
          {messages.length === 0 && (
            <div className="mt-10 text-center">
              <h2 className="text-sm font-semibold text-slate-500">问点什么，从代码里找答案</h2>
              <p className="mt-1.5 text-xs leading-relaxed text-slate-400">
                问代码，比如「对话流在哪个文件实现？」，答案会指出具体位置，点开就能看到源码。
                <br />
                问概念，比如「SQL 是什么？」，答案里的链接可以打开教材继续读。
              </p>
            </div>
          )}
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
