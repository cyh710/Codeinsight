/**
 * `applySseEvent` 事件规约测试：UI 行为的关键不变量都在这里锁住——
 * 事实与推断分栏、error 不中断、done 统一收尾、工具时间线不重复。
 */
import { describe, expect, it } from 'vitest'
import { applySseEvent } from '../src/store/chatStore'
import type { ChatMessage } from '../src/store/types'

const AID = 'a1'

function seed(): ChatMessage[] {
  return [
    { id: 'u1', role: 'user', text: '问个问题', timestamp: '' },
    { id: AID, role: 'assistant', text: '', streaming: true, timestamp: '' },
  ]
}

function assistant(messages: ChatMessage[]): ChatMessage {
  return messages.find((m) => m.id === AID)!
}

describe('applySseEvent', () => {
  it('delta 追加文本，evidence 积累，边流边有', () => {
    let msgs = seed()
    msgs = applySseEvent(msgs, AID, { event: 'delta', data: { text: '你好' } })
    msgs = applySseEvent(msgs, AID, { event: 'delta', data: { text: '，代码在这' } })
    msgs = applySseEvent(msgs, AID, {
      event: 'evidence',
      data: { path: 'a.py', lineno: 1, end_lineno: 2, qualname: 'a.f', snippet: 'def f', lanes: ['bm25'], concepts: [] },
    })
    const a = assistant(msgs)
    expect(a.text).toBe('你好，代码在这')
    expect(a.evidence).toHaveLength(1)
    expect(a.evidence?.[0].path).toBe('a.py')
  })

  it('工具时间线：running → ok 更新同一行，不追加新行', () => {
    let msgs = seed()
    msgs = applySseEvent(msgs, AID, { event: 'tool', data: { name: 'search_code', status: 'running', summary: '搜索' } })
    msgs = applySseEvent(msgs, AID, { event: 'tool', data: { name: 'search_code', status: 'ok', summary: '命中 3' } })
    expect(assistant(msgs).tools).toEqual([
      { name: 'search_code', status: 'ok', summary: '命中 3' },
    ])
  })

  it('两个不同工具各占一行', () => {
    let msgs = seed()
    msgs = applySseEvent(msgs, AID, { event: 'tool', data: { name: 'search_code', status: 'ok', summary: '' } })
    msgs = applySseEvent(msgs, AID, { event: 'tool', data: { name: 'get_callers', status: 'running', summary: '' } })
    expect(assistant(msgs).tools).toHaveLength(2)
  })

  it('answer 落定 facts/inferences（分栏数据源），不结束流', () => {
    let msgs = seed()
    msgs = applySseEvent(msgs, AID, {
      event: 'answer',
      data: {
        facts: [{ text: 'f1', citation: { path: 'a.py', lineno: 1, end_lineno: 2, qualname: null, snippet: '' } }],
        inferences: [{ text: 'i1', confidence: 0.7 }],
        citations: [],
        abstained: false,
        reason: '',
      },
    })
    const a = assistant(msgs)
    expect(a.facts).toHaveLength(1)
    expect(a.inferences).toHaveLength(1)
    expect(a.streaming).toBe(true)
  })

  it('error 只记录不收尾；随后的 done 收尾并保留 error 信息', () => {
    let msgs = seed()
    msgs = applySseEvent(msgs, AID, {
      event: 'error',
      data: { code: 'upstream_error', title: '上游 502', hint: '重试' },
    })
    expect(assistant(msgs).streaming).toBe(true)
    expect(assistant(msgs).error?.code).toBe('upstream_error')
    msgs = applySseEvent(msgs, AID, { event: 'done', data: { abstained: false, reason: '' } })
    const a = assistant(msgs)
    expect(a.streaming).toBe(false)
    expect(a.error?.code).toBe('upstream_error')
  })

  it('answer 带 incomplete 时落到消息上（与 abstained 分开）', () => {
    let msgs = seed()
    msgs = applySseEvent(msgs, AID, {
      event: 'answer',
      data: {
        facts: [],
        inferences: [],
        citations: [],
        abstained: false,
        reason: '',
        incomplete: true,
      },
    })
    const a = assistant(msgs)
    expect(a.incomplete).toBe(true)
    expect(a.abstained).toBe(false)
  })

  it('done 携带弃答信息', () => {
    let msgs = seed()
    msgs = applySseEvent(msgs, AID, { event: 'done', data: { abstained: true, reason: '检索无命中' } })
    const a = assistant(msgs)
    expect(a.streaming).toBe(false)
    expect(a.abstained).toBe(true)
    expect(a.abstentionReason).toBe('检索无命中')
  })
})
