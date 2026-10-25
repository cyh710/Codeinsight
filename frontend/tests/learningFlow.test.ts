import { afterEach, describe, expect, it, vi } from 'vitest'
import { createStore } from 'zustand'
import { workbenchStore, panelKey } from '../src/store/workbenchStore'
import { createChatActions, applySseEvent } from '../src/store/chatStore'
import { api } from '../src/api/dataSource'
import type { ChatStore, ChatMessage } from '../src/store/types'
import type { LearningTarget, SseEvent } from '../src/api/types'
import { resolveLearningLink } from '../src/components/learning/links'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import MessageBubble from '../src/components/chat/MessageBubble'

const sql: LearningTarget = {
  topic_id: 'sql-database',
  section_id: 'example',
  title: 'SQL',
  version: 'v1',
  href: '/learn/sql-database#example',
}
afterEach(() => {
  vi.restoreAllMocks()
  workbenchStore.getState().resetProject()
})

it('教材代码原样呈现，不把指数运算符或代码内学习地址改写成链接', () => {
  const html = renderToStaticMarkup(
    createElement(MessageBubble, {
      message: {
        id: 'a',
        role: 'assistant',
        timestamp: '',
        text: '```python\nx ** 2\n[SQL](/learn/sql-database#example)\n```',
        learningTargets: [sql],
      },
      onOpenCitation: () => {},
    }),
  )
  expect(html).toContain('x ** 2')
  expect(html).not.toContain('\u200b')
  expect(html).not.toContain('href="/learn/')
})

describe('知识与代码往返', () => {
  it('恢复来路、阅读位置和目标；项目切换丢弃旧代码上下文', () => {
    const s = workbenchStore.getState()
    s.resetProject()
    s.selectFile('store.py', 4)
    s.setReading({ kind: 'code', project_id: 1, path: 'store.py', lineno: 4 })
    s.saveScroll(panelKey(workbenchStore.getState().rightPanel), 320)
    s.openKnowledge(sql)
    s.setReading({
      kind: 'knowledge',
      topic_id: sql.topic_id,
      section_id: sql.section_id,
      version: sql.version,
    })
    const articleKey = panelKey(workbenchStore.getState().rightPanel)
    s.saveScroll(articleKey, 850)
    s.openKnowledgeTree()
    s.goBack()
    expect(workbenchStore.getState().rightPanel).toEqual({ mode: 'knowledge', target: sql })
    expect(workbenchStore.getState().scrollPositions[articleKey]).toBe(850)
    expect(workbenchStore.getState().reading?.kind).toBe('knowledge')
    s.returnToCode()
    expect(workbenchStore.getState().reading).toMatchObject({
      kind: 'code',
      project_id: 1,
      path: 'store.py',
    })
    expect(
      workbenchStore.getState().scrollPositions[panelKey(workbenchStore.getState().rightPanel)],
    ).toBe(320)
    s.goForward()
    expect(workbenchStore.getState().rightPanel.mode).toBe('knowledge')
    s.resetProject()
    expect(workbenchStore.getState().reading).toBeNull()
    expect(workbenchStore.getState().selectedPath).toBeNull()
    expect(workbenchStore.getState().history).toHaveLength(1)
  })

  it('未完成链接、流中链接和未解析目标不可点击', () => {
    expect(resolveLearningLink('/learn/sql-database#example', [sql], true)).toBeNull()
    expect(resolveLearningLink('/learn/sql-dat', [sql])).toBeNull()
    expect(resolveLearningLink('/learn/ghost', [sql])).toBeNull()
    expect(resolveLearningLink('https://other/learn/sql-database#example', [sql])).toBeNull()
    expect(resolveLearningLink(sql.href, [sql])).toEqual(sql)
  })
})

it('最终 SSE 文本替换未校验增量，并带来源与最多三个入口的原始元数据', () => {
  const seed: ChatMessage[] = [
    { id: 'a', role: 'assistant', timestamp: '', text: '[SQL](/learn/sql-', streaming: true },
  ]
  const messages = applySseEvent(seed, 'a', {
    event: 'answer',
    data: {
      text: '[SQL](/learn/sql-database#example)',
      facts: [],
      inferences: [],
      citations: [],
      abstained: false,
      reason: '',
      incomplete: false,
      learning_entries: [sql],
      learning_targets: [sql],
      knowledge_sources: [{ target: sql, snippet: '教材正文', score: 1, sources: [] }],
    },
  })
  expect(messages[0].text).toBe('[SQL](/learn/sql-database#example)')
  expect(messages[0].learningTargets).toEqual([sql])
  expect(messages[0].knowledgeSources?.[0].target.version).toBe('v1')
})

it('切换项目保留原对话，旧流的后续事件不能写入新项目', async () => {
  let emit: ((event: SseEvent) => void) | undefined
  let finish: ((value: { aborted: boolean }) => void) | undefined
  const request = vi.spyOn(api, 'streamQuery').mockImplementation((_body, callback) => {
    emit = callback
    return new Promise((resolve) => {
      finish = resolve
    })
  })
  const store = createStore<ChatStore>((set, get) => ({
    messages: [],
    streaming: false,
    conversationId: '',
    _abortController: null,
    ...createChatActions(set, get),
  }))
  store.getState().switchProject(1)
  workbenchStore
    .getState()
    .setReading({
      kind: 'knowledge',
      topic_id: sql.topic_id,
      section_id: sql.section_id,
      version: sql.version,
    })
  const pending = store.getState().sendMessage(1, '这里是什么意思')
  expect(request.mock.calls[0][0].reading_context).toMatchObject({ topic_id: sql.topic_id })
  store.getState().switchProject(2)
  emit?.({ event: 'delta', data: { text: '旧项目后续内容' } })
  finish?.({ aborted: true })
  await pending
  expect(store.getState().messages).toEqual([])
  store.getState().switchProject(1)
  expect(store.getState().messages[0].text).toBe('这里是什么意思')
  expect(store.getState().messages.some((m) => m.text.includes('旧项目后续内容'))).toBe(true)
  expect(store.getState().streaming).toBe(false)
})
