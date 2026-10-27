import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { expect, it } from 'vitest'
import MessageBubble from '../src/components/chat/MessageBubble'
import { additionalExplanation } from '../src/components/learning/explanation'
import { applySseEvent } from '../src/store/chatStore'

it('旧回答保留正文与元数据，但不再呈现全篇评级、分类与百分比', () => {
  const html = renderToStaticMarkup(createElement(MessageBubble, {
    message: { id: 'old', role: 'assistant', timestamp: '', text: '先看策略怎样组织证据。成绩记录还没有找到。',
      abstained: true, abstentionReason: '旧全篇提示',
      evidenceReview: { status: 'partial', message: '旧全篇提示', checks: [], unverified_citations: [] },
      facts: [{ text: '组织证据', citation: { path: 'app.py', lineno: 1, end_lineno: 1, qualname: null, snippet: '' } }],
      inferences: [{ text: '先看策略怎样组织证据。', confidence: 0.5 }] },
    onOpenCitation: () => {},
  }))
  expect(html).toContain('成绩记录还没有找到')
  expect(html).toContain('来源与查阅过程')
  expect(html).not.toMatch(/旧全篇提示|代码事实|推断（待核对）|50%/)
})

it('旧概念独有解读不丢失，已存在正文中的解读不重复', () => {
  expect(additionalExplanation('签名**验证**保护完整性。', [
    { text: '签名验证保护完整性。' }, { text: '过期检查还需核对调用参数。' },
    { text: '过期检查还需核对调用参数。' }, { text: '   ' },
  ])).toEqual(['过期检查还需核对调用参数。'])
})

it('流式最终材料含源码查阅窗口，刷新前即可展示且不授予正文引用身份', () => {
  const messages = applySseEvent([{ id: 'a', role: 'assistant', timestamp: '', text: '', streaming: true }], 'a', {
    event: 'answer', data: { text: '接收值后保存。', facts: [], inferences: [], citations: [], abstained: false, reason: '', incomplete: false,
      evidence: [{ path: 'store.py', lineno: 1, end_lineno: 8, qualname: null, snippet: 'def save(value):', lanes: [], concept_ids: [] }] },
  })
  expect(messages[0].evidence?.[0]).toMatchObject({ path: 'store.py', snippet: 'def save(value):', concepts: [] })
  expect(messages[0].citations).toEqual([])
})
