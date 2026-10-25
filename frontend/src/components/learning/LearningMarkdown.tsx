/** 站内学习链接仅接受服务端解析目标；流式未落定时保持普通文字。 */
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { LearningTarget } from '../../api/types'
import { workbenchStore } from '../../store/workbenchStore'
import { resolveLearningLink } from './links'
import './reading.css'
import { sourcePositions } from './selection'

export default function LearningMarkdown({
  text,
  targets = [],
  streaming = false,
  selectable = false,
}: {
  text: string
  targets?: LearningTarget[]
  streaming?: boolean
  selectable?: boolean
}) {
  return (
    <div className="learning-prose">
      <Markdown
        remarkPlugins={selectable ? [remarkGfm, sourcePositions] : [remarkGfm]}
        components={{
          a: ({ href, children }) => {
            if (href?.startsWith('/learn/')) {
              const target = resolveLearningLink(href, targets, streaming)
              return target ? (
                <a
                  href={target.href}
                  className="inline text-accent underline decoration-accent/35 underline-offset-4 hover:decoration-accent"
                  onClick={(event) => {
                    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return
                    event.preventDefault()
                    workbenchStore.getState().openKnowledge(target)
                  }}
                >
                  {children}
                </a>
              ) : (
                <span>{children}</span>
              )
            }
            return href && /^https?:\/\//.test(href) ? (
              <a
                href={href}
                target="_blank"
                rel="noreferrer"
                className="text-accent underline underline-offset-4"
              >
                {children}
              </a>
            ) : (
              <span>{children}</span>
            )
          },
          table: ({ children }) => (
            <div className="my-3 overflow-x-auto">
              <table className="w-full border-collapse text-left text-xs">{children}</table>
            </div>
          ),
          // 引用块在教材里当「答案块」用：自测章节的答案写在这里，
          // 给它边框和底色，读者一眼能看出哪段是答案。
          blockquote: ({ children }) => (
            <blockquote className="my-3 rounded-lg border-l-2 border-accent/40 bg-accent-soft/30 px-3 py-2 text-slate-700">
              {children}
            </blockquote>
          ),
        }}
      >
        {text}
      </Markdown>
    </div>
  )
}
