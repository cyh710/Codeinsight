/**
 * 输入框：Enter 发送、Shift+Enter 换行；流式进行中变为"停止"。
 * 织忆的图片粘贴/语音/模式切换都不带过来（CodeInsight 用不上）。
 */
import { useLayoutEffect, useRef } from 'react'
import { useStore } from 'zustand'
import { Send, Square, X } from 'lucide-react'
import { chatStore } from '../../store/chatStore'
import { projectStore } from '../../store/projectStore'
import { workbenchStore } from '../../store/workbenchStore'

export default function InputBox() {
  const streaming = useStore(chatStore, (s) => s.streaming)
  const projectId = useStore(projectStore, (s) => s.currentProjectId)
  const reading = useStore(workbenchStore, (s) => s.reading)
  const mode = useStore(workbenchStore, (s) => s.readingMode)
  const value = useStore(chatStore, (s) => s.draft)
  const loading = useStore(chatStore, (s) => s.loading)
  const setValue = chatStore.getState().setDraft
  const taRef = useRef<HTMLTextAreaElement>(null)
  useLayoutEffect(() => {
    const el = taRef.current
    if (el) { el.style.height = 'auto'; el.style.height = `${Math.min(160, el.scrollHeight)}px` }
  }, [value])

  const submit = () => {
    const question = value.trim()
    if (!question || streaming || projectId === null) return
    setValue('')
    void chatStore.getState().sendMessage(projectId, question)
    taRef.current?.focus()
  }

  return (
    <div className="chat-composer">
        <div className="reading-context mb-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500">
          <span className="min-w-0 truncate" title={reading?.preview}>
            {reading ? (reading.kind === 'knowledge'
              ? `${reading.title ?? reading.topic_id}${reading.section_title ? ` · ${reading.section_title}` : ''}`
              : `${reading.path.split('/').at(-1)}:${reading.lineno}${reading.end_lineno ? `–${reading.end_lineno}` : ''}`) : '未关联材料'}
            {reading?.selection ? ' · 已选择具体段落' : ''}
            {reading ? ` · ${mode === 'fixed' ? '已固定' : '跟随阅读'}` : ''}
          </span>
          {reading && mode === 'follow' && <button type="button" onClick={() => workbenchStore.getState().fixReading()} className="text-accent" title="切换阅读时保留这个提问目标">固定提问目标</button>}
          {mode !== 'follow' && <button type="button" onClick={() => workbenchStore.getState().followReading()} className="text-accent">跟随阅读</button>}
          {reading?.preview && <details className="w-full"><summary className="cursor-pointer">查看选区</summary><pre className="max-h-28 overflow-auto whitespace-pre-wrap rounded bg-slate-100 p-2">{reading.preview}</pre></details>}
          {reading &&
          <button
            aria-label="取消关联"
            title="取消关联"
            className="wb-icon-button ml-auto text-slate-400 hover:text-accent"
            onClick={() => workbenchStore.getState().setReading(null)}
          >
            <X size={15} />
          </button>}
        </div>
      <div className="flex items-end gap-2 rounded-2xl border border-[var(--chat-input-border)] bg-[var(--chat-input-background)] px-3 py-2 shadow-[var(--chat-input-shadow)]">
        <textarea
          ref={taRef}
          rows={1}
          className="max-h-40 min-h-[24px] flex-1 resize-none bg-transparent text-sm leading-relaxed text-slate-800 outline-none placeholder:text-slate-400"
          placeholder={
            projectId === null
              ? '先在左栏选择一个项目…'
              : reading?.selection ? '这段内容，你想了解什么？' : reading ? '针对当前材料继续问…' : '问代码，或探索一个概念…'
          }
          value={value}
          disabled={loading || projectId === null}
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
            disabled={!value.trim() || projectId === null || loading}
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
