import type { ChatMessage } from '../../store/types'

export function AnswerReviewDetails({ message }: { message: ChatMessage }) {
  if (message.streaming || (!message.evidenceReview && !message.rawText)) return null
  const review = message.evidenceReview
  return <details className="mt-2 text-xs leading-6 text-slate-500">
    <summary className="cursor-pointer py-1">查阅记录</summary>
    {!!review?.checks.length && <ul className="my-2 list-inside list-disc">{review.checks.map((check, index) =>
      <li key={index}>{check.target || check.tool} · {{ matched: '取得位置', no_match: '本次未命中', unavailable: '读取未完成' }[check.status]}</li>)}</ul>}
    {!!review?.unverified_citations.length && <p>无法定位的引用（不能跳转）：{review.unverified_citations.join('、')}</p>}
    {message.rawText && <details className="mt-2"><summary className="cursor-pointer">生成原文</summary><pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-md bg-slate-50 p-3 font-sans text-xs leading-6">{message.rawText}</pre></details>}
  </details>
}
