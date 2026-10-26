import type { ChatMessage } from '../../store/types'

/** 正文始终可读，核查状态只提示证据范围，不代替用户阅读。 */
export function AnswerReviewNotice({ message }: { message: ChatMessage }) {
  const review = message.evidenceReview
  if (message.streaming || message.responseKind === 'clarification') return null
  const hint = review && !['verified', 'knowledge'].includes(review.status) ? review.message
    : !review && message.abstained ? message.abstentionReason || '这份回答尚未取得可核实的项目依据。' : ''
  return hint ? <p role="status" className="mb-3 border-l-2 border-amber-200 pl-3 text-xs leading-6 text-slate-500">{hint}</p> : null
}

export function AnswerReviewDetails({ message }: { message: ChatMessage }) {
  if (message.streaming || (!message.evidenceReview && !message.rawText)) return null
  const review = message.evidenceReview
  return <details className="mt-2 text-xs leading-6 text-slate-500">
    <summary className="cursor-pointer py-1">核查与生成原文</summary>
    {review && <p>{review.message}</p>}
    {!!review?.checks.length && <ul className="my-2 list-inside list-disc">{review.checks.map((check, index) =>
      <li key={index}>{check.target || check.tool} · {{ matched: '取得来源', no_match: '本次未命中', unavailable: '读取未完成' }[check.status]}</li>)}</ul>}
    {!!review?.unverified_citations.length && <p>未核实位置（不能跳转）：{review.unverified_citations.join('、')}</p>}
    {message.rawText && <><p className="mt-2">生成原文 · 其中引用未经核实，仅供回看</p><pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-md bg-slate-50 p-3 font-sans text-xs leading-6">{message.rawText}</pre></>}
  </details>
}
