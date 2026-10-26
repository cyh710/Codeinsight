import { afterEach, expect, it, vi } from 'vitest'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createStore } from 'zustand'
import LearningMarkdown from '../src/components/learning/LearningMarkdown'
import { workbenchStore, materialKey } from '../src/store/workbenchStore'
import { api } from '../src/api/dataSource'
import { createChatActions } from '../src/store/chatStore'
import type { ChatStore } from '../src/store/types'

afterEach(() => { vi.restoreAllMocks(); workbenchStore.getState().resetProject() })

it('只对已校验正文引用编号，代码、行内代码和已有链接保持原样', () => {
  const html = renderToStaticMarkup(createElement(LearningMarkdown, {
    text: '真实依据 [app.py:4]。未知 [fake.py:9]。\n\n- 中文列表😀 [app.py:4]\n\n| 依据 | 位置 |\n|---|---|\n| 已核对 | [app.py:4] |\n\n`[app.py:4]`\n\n```py\n[app.py:4]\n```\n\n[已有链接 [app.py:4]](https://example.com)',
    citations: [{ path: 'app.py', lineno: 4, end_lineno: 4, qualname: null, snippet: '' }], onCitation: () => {},
  }))
  expect(html).toContain('exploration-citation')
  expect(html).toContain('>[1]</button>')
  expect(html).toContain('[fake.py:9]')
  expect(html).toContain('<code>[app.py:4]</code>')
  expect(html).toContain('已有链接 [app.py:4]')
  expect(html.match(/class="exploration-citation"/g)).toHaveLength(3)
  const partial = renderToStaticMarkup(createElement(LearningMarkdown, { text: '[app.py:4]', streaming: true,
    citations: [{ path: 'app.py', lineno: 4, end_lineno: 4, qualname: null, snippet: '' }], onCitation: () => {} }))
  expect(partial).not.toContain('exploration-citation')
})

it('直接追问保留草稿、关联与请求去重，并阻止同会话重复启动', async () => {
  let finish!: (result: { aborted: boolean }) => void
  const request = vi.spyOn(api, 'streamQuery').mockImplementation(() => new Promise(resolve => { finish = resolve }))
  const store = createStore<ChatStore>((set, get) => ({ messages: [], streaming: false, conversationId: '', _abortController: null, ...createChatActions(set, get) }))
  await store.getState().switchProject(1)
  const original = { kind: 'code' as const, project_id: 1, path: 'draft.py', lineno: 8 }
  workbenchStore.getState().fixReading(original)
  store.getState().setDraft('尚未写完的中文草稿😀')
  const target = { kind: 'code' as const, project_id: 1, path: 'app.py', lineno: 4 }
  const pending = store.getState().sendMessage(1, '解释写入', { preserveDraft: true, reading: target })
  await store.getState().sendMessage(1, '解释写入', { preserveDraft: true, reading: target })
  expect(request).toHaveBeenCalledTimes(1)
  expect(request.mock.calls[0][0].reading_context).toEqual(target)
  expect(store.getState().draft).toBe('尚未写完的中文草稿😀')
  expect(workbenchStore.getState().reading).toEqual(original)
  finish({ aborted: true }); await pending
  expect(store.getState().draft).toBe('尚未写完的中文草稿😀')
  expect(workbenchStore.getState().reading).toEqual(original)
})

it('不同来源回合的局部解读不复用同一材料身份，全文仍按版本复用', () => {
  const target = { topic_id: 'sql-database', section_id: 'overview', title: 'SQL', version: 'v1', href: '/learn/sql-database' }
  const a = { mode: 'exploration' as const, projectId: 1, conversationId: 'c', requestId: 'r1', target }
  expect(materialKey(a)).not.toBe(materialKey({ ...a, requestId: 'r2' }))
  expect(materialKey({ mode: 'knowledge', target })).toBe(materialKey({ mode: 'knowledge', target: { ...target, section_id: 'example' } }))
})
