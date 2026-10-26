/**
 * 输入框：Enter 发送、Shift+Enter 换行；流式进行中变为"停止"。
 * 织忆的图片粘贴/语音/模式切换都不带过来（CodeInsight 用不上）。
 */
import { useLayoutEffect, useRef } from 'react'
import { useStore } from 'zustand'
import { BookOpen, Code2, Pin, RotateCcw, Send, Square, X } from 'lucide-react'
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
  const readingTitle = reading ? reading.kind === 'knowledge'
    ? `${reading.title ?? reading.topic_id}${reading.section_title ? ` · ${reading.section_title}` : ''}`
    : `${reading.path}:${reading.lineno}${reading.end_lineno ? `–${reading.end_lineno}` : ''}` : ''
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
      {(reading || mode !== 'follow') && <div className="reading-context" role="group" aria-label="提问关联">
        {reading ? <>
          <details className="reading-target"><summary title={readingTitle} aria-label={reading.preview ? '查看选区' : '查看关联材料'}>
            {reading.kind === 'knowledge' ? <BookOpen size={14} aria-hidden="true" /> : <Code2 size={14} aria-hidden="true" />}
            <span>{reading.kind === 'knowledge' ? reading.section_title ?? reading.title ?? reading.topic_id : `${reading.path.split('/').at(-1)}:${reading.lineno}${reading.end_lineno ? `–${reading.end_lineno}` : ''}`}</span>
          </summary><div className="reading-target-preview"><p>{readingTitle}</p>{reading.preview && <pre>{reading.preview}</pre>}</div></details>
          <button type="button" aria-label="固定提问目标" aria-pressed={mode === 'fixed'} title={mode === 'fixed' ? '已固定；点击恢复跟随阅读' : '固定提问目标'} className="wb-icon-button" onClick={() => mode === 'fixed' ? workbenchStore.getState().followReading() : workbenchStore.getState().fixReading()}><Pin size={14} /></button>
          <button type="button" aria-label="取消关联" title="取消关联" className="wb-icon-button" onClick={() => workbenchStore.getState().setReading(null)}><X size={15} /></button>
        </> : <button type="button" className="wb-button" title="重新关联当前阅读的材料" onClick={() => workbenchStore.getState().followReading()}><RotateCcw size={14} />跟随阅读</button>}
      </div>}
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
