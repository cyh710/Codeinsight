import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { expect, it } from 'vitest'
import MessageBubble from '../src/components/chat/MessageBubble'
import { applySseEvent, turnMessages } from '../src/store/chatStore'
import type { AnswerEvidenceReview } from '../src/api/types'

const review: AnswerEvidenceReview = { status: 'unverified', message: '本轮尚未取得有效代码引用。',
  checks: [], unverified_citations: ['ghost.py:99'], source_version: null }

it('依据不足仍展示完整正文，原文只作文字回看，旧弃答正文也不隐藏', () => {
  const html = renderToStaticMarkup(createElement(MessageBubble, {
    message: { id: 'a', role: 'assistant', timestamp: '', text: '先把它想成一个收件窗口。 `未核实位置：ghost.py:99`',
      abstained: true, evidenceReview: review, rawText: '先把它想成一个收件窗口。 [ghost.py:99]' }, onOpenCitation: () => {},
  }))
  expect(html).toContain('收件窗口')
  expect(html).toContain('本轮尚未取得有效代码引用')
  expect(html).toContain('<pre')
  expect(html).not.toContain('href=')
  const legacy = renderToStaticMarkup(createElement(MessageBubble, {
    message: { id: 'old', role: 'assistant', timestamp: '', text: '旧记录中保留的解释。', abstained: true }, onOpenCitation: () => {},
  }))
  expect(legacy).toContain('旧记录中保留的解释')
})

it('SSE 收尾保留正文与核查元数据，不因为 abstained 切换为占位文本', () => {
  let messages = applySseEvent([{ id: 'a', role: 'assistant', timestamp: '', text: '', streaming: true }], 'a',
    { event: 'delta', data: { text: '可以先这样理解。' } })
  messages = applySseEvent(messages, 'a', { event: 'answer', data: { text: '可以先这样理解。', raw_text: '可以先这样理解。',
    evidence_review: review, response_kind: 'rephrase', facts: [], inferences: [], citations: [], abstained: true, reason: review.message, incomplete: false } })
  messages = applySseEvent(messages, 'a', { event: 'done', data: { abstained: true, reason: review.message } })
  expect(messages[0]).toMatchObject({ text: '可以先这样理解。', streaming: false, rawText: '可以先这样理解。',
    responseKind: 'rephrase', evidenceReview: review })
})

it('持久化回合恢复时保留生成原文及核查状态', () => {
  const [, answer] = turnMessages({ request_id: 'r', task_id: null,
    question: '听不懂', reading_context: null, status: 'abstained', legacy: false, created_at: '',
    answer: { text: '已保存解释', raw_text: '未删改原文', evidence_review: review, response_kind: 'rephrase', abstained: true } })
  expect(answer).toMatchObject({ text: '已保存解释', rawText: '未删改原文', evidenceReview: review, responseKind: 'rephrase' })
})
