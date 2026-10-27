import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { expect, it, vi } from 'vitest'
import LearningMarkdown from '../src/components/learning/LearningMarkdown'
import MessageBubble from '../src/components/chat/MessageBubble'
import type { Citation } from '../src/api/types'

const citation: Citation = { path: 'wattbot-nlp/src/dense/hybrid.py', lineno: 19, end_lineno: 19, qualname: null, snippet: '' }

it('单行和范围引用显示文件名链接，目标仍是服务端核对的位置', () => {
  const href = vi.fn(() => '/?project=6&conversation=c&material=verified')
  const html = renderToStaticMarkup(createElement(LearningMarkdown, { variant: 'answer',
    text: '来源 [wattbot-nlp/src/dense/hybrid.py:19-23] 和 [wattbot-nlp/src/dense/hybrid.py:19]，未知 [ghost.py:9-12]。',
    citations: [citation], onCitation: () => {}, citationHref: href,
  }))
  expect(html).toContain('hybrid.py:19–23</a>')
  expect(html).toContain('hybrid.py:19</a>')
  expect(html).toContain('title="wattbot-nlp/src/dense/hybrid.py:19"')
  expect(html).toContain('href="/?project=6&amp;conversation=c')
  expect(html).toContain('[ghost.py:9-12]')
  expect(href).toHaveBeenCalledWith(citation)
  expect(citation.end_lineno).toBe(19)
})

it('流式和代码中的引用不启用，既有链接不嵌套改写', () => {
  const props = { variant: 'answer' as const, citations: [citation], onCitation: () => {} }
  const partial = renderToStaticMarkup(createElement(LearningMarkdown, { ...props,
    text: '[wattbot-nlp/src/dense/hybrid.py:19-23]', streaming: true }))
  expect(partial).not.toContain('reply-citation')
  const code = renderToStaticMarkup(createElement(LearningMarkdown, { ...props,
    text: '`[wattbot-nlp/src/dense/hybrid.py:19-23]`\n\n```py\n[wattbot-nlp/src/dense/hybrid.py:19-23]\n```\n\n[已有链接 [wattbot-nlp/src/dense/hybrid.py:19-23]](https://example.com)' }))
  expect(code).not.toContain('reply-citation')
  expect(code).toContain('href="https://example.com"')
  expect(code).toContain('<code>[wattbot-nlp/src/dense/hybrid.py:19-23]</code>')
})

it('旧回答没有探索字段仍渲染可点击引用，不隐藏正文', () => {
  const html = renderToStaticMarkup(createElement(MessageBubble, {
    message: { id: 'legacy', role: 'assistant', timestamp: '', citations: [citation],
      text: '这是实现 [wattbot-nlp/src/dense/hybrid.py:19-23]。' }, onOpenCitation: () => {},
  }))
  expect(html).toContain('learning-prose--answer')
  expect(html).toContain('reply-citation')
  expect(html).toContain('hybrid.py:19–23')
})

it('回答代码块提供语言和复制，教材保留原代码布局', () => {
  const text = '```python\nprint("中文😀")\n```'
  const reply = renderToStaticMarkup(createElement(LearningMarkdown, { text, variant: 'answer' }))
  expect(reply).toContain('reply-code-toolbar')
  expect(reply).toContain('aria-label="复制代码"')
  expect(reply).toContain('<span>python</span>')
  const article = renderToStaticMarkup(createElement(LearningMarkdown, { text }))
  expect(article).not.toContain('reply-code-toolbar')
  expect(article).toContain('<pre>')
})
