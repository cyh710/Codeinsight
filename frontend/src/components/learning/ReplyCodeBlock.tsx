import { Children, isValidElement, useState, type ReactNode } from 'react'
import { Check, Copy } from 'lucide-react'

/** 复制完整代码原文，横向滚动仅留在代码块内。 */
export default function ReplyCodeBlock({ children }: { children: ReactNode }) {
  const code = Children.toArray(children).find(child => isValidElement(child))
  const props = isValidElement<{ className?: string; children?: ReactNode }>(code) ? code.props : undefined
  const language = props?.className?.match(/(?:^|\s)language-([\w+-]+)/)?.[1] ?? ''
  const text = typeof props?.children === 'string' ? props.children : ''
  const [status, setStatus] = useState('复制')
  return <div className="reply-code-block">
    <div className="reply-code-toolbar">
      <span>{language}</span>
      <button type="button" aria-label="复制代码" onClick={() => {
        void navigator.clipboard.writeText(text).then(() => setStatus('已复制'), () => setStatus('复制失败'))
      }}>
        {status === '已复制' ? <Check size={14} /> : <Copy size={14} />}
        <span role="status">{status}</span>
      </button>
    </div>
    <pre>{children}</pre>
  </div>
}
