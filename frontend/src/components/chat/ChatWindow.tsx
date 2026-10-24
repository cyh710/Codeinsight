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

export default function ChatWindow({ onOpenCitation }: { onOpenCitation: (c: Citation) => void }) {
  const messages = useStore(chatStore, (s) => s.messages)
  const scrollRef = useRef<HTMLDivElement>(null)
  const anchorRef = useRef<HTMLDivElement>(null)
  const wasAtBottomRef = useRef(true)

  // 流式增量到来时吸底；用户翻离底部则停止跟随。
  useLayoutEffect(() => {
    if (!wasAtBottomRef.current) return
    anchorRef.current?.scrollIntoView({ block: 'end' })
  }, [messages])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const onScroll = () => {
      wasAtBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48
    }
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <section className="flex h-full min-h-0 min-w-0 flex-1 flex-col bg-bg">
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <div className="mx-auto flex max-w-3xl flex-col gap-3">
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
            <MessageBubble key={m.id} message={m} onOpenCitation={onOpenCitation} />
          ))}
          <div ref={anchorRef} />
        </div>
      </div>
      <InputBox />
    </section>
  )
}
