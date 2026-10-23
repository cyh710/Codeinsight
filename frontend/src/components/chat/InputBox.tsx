/**
 * 输入框：Enter 发送、Shift+Enter 换行；流式进行中变为"停止"。
 * 织忆的图片粘贴/语音/模式切换都不带过来（CodeInsight 用不上）。
 */
import { useRef, useState } from 'react'
import { useStore } from 'zustand'
import { Send, Square } from 'lucide-react'
import { chatStore } from '../../store/chatStore'
import { projectStore } from '../../store/projectStore'

export default function InputBox() {
  const streaming = useStore(chatStore, (s) => s.streaming)
  const projectId = useStore(projectStore, (s) => s.currentProjectId)
  const [value, setValue] = useState('')
  const taRef = useRef<HTMLTextAreaElement>(null)

  const submit = () => {
    const question = value.trim()
    if (!question || streaming || projectId === null) return
    setValue('')
    void chatStore.getState().sendMessage(projectId, question)
    taRef.current?.focus()
  }

  return (
    <div className="border-t border-slate-200/70 bg-bg-elevated/80 px-4 py-3">
      <div className="flex items-end gap-2 rounded-2xl border border-[var(--chat-input-border)] bg-[var(--chat-input-background)] px-3 py-2 shadow-[var(--chat-input-shadow)]">
        <textarea
          ref={taRef}
          rows={1}
          className="max-h-40 min-h-[24px] flex-1 resize-none bg-transparent text-sm leading-relaxed text-slate-800 outline-none placeholder:text-slate-400"
          placeholder={projectId === null ? '先在左栏选择一个项目…' : '问这个项目的代码，例如：对话流程是怎么走的？'}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault()
              submit()
            }
          }}
        />
        {streaming ? (
          <button
            type="button"
            onClick={() => chatStore.getState().stopStreaming()}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-danger/40 text-danger transition-colors hover:bg-danger-soft"
            title="停止生成"
            aria-label="停止生成"
          >
            <Square size={13} strokeWidth={2} />
          </button>
        ) : (
          <button
            type="button"
            onClick={submit}
            disabled={!value.trim() || projectId === null}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-accent text-accent-foreground transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
            title="发送（Enter）"
            aria-label="发送"
          >
            <Send size={14} strokeWidth={1.8} />
          </button>
        )}
      </div>
    </div>
  )
}
