/**
 * 编排执行的前端规约与渲染测试（契约 §16.2）。
 * 规约不变量：answer.execution 落到消息；普通问答 execution 为 null。
 */
import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { applySseEvent } from '../src/store/chatStore'
import type { ChatMessage } from '../src/store/types'
import type { ExecutionMetadata } from '../src/api/types'
import ExecutionCard from '../src/components/execution/ExecutionCard'

const AID = 'a1'

function seed(): ChatMessage[] {
  return [
    { id: 'u1', role: 'user', text: '帮我加限流', timestamp: '' },
    { id: AID, role: 'assistant', text: '', streaming: true, timestamp: '' },
  ]
}

function metaOf(status: ExecutionMetadata['status'], extra: Partial<ExecutionMetadata> = {}): ExecutionMetadata {
  return {
    task_id: 'exec-ab12',
    status,
    plan: { intent: '加限流', files: ['app.py'], approach: '改主循环', risks: ['误伤'] },
    progress: [{ kind: 'tool', tool: 'Edit', file: 'app.py', detail: '' }],
    diff_summary:
      status === 'review' || status === 'merged'
        ? { files_changed: 1, insertions: 3, deletions: 1, files: [{ path: 'app.py', status: 'modified', add: 3, del: 1 }] }
        : null,
    change_card:
      status === 'merged'
        ? {
            facts: [
              { text: 'app.main：body_changed', citation: { path: 'app.py', lineno: 1, end_lineno: 2, qualname: 'app.main', snippet: '' } },
            ],
            impacted: { modules: ['app'], symbols: [] },
            concept_ids: ['decorator'],
          }
        : null,
    summary: status === 'review' || status === 'merged' ? '改完了' : '',
    ...extra,
  }
}

describe('applySseEvent · execution', () => {
  it('answer 带 execution 时落到消息上', () => {
    const meta = metaOf('planned')
    const msgs = applySseEvent(seed(), AID, {
      event: 'answer',
      data: {
        facts: [],
        inferences: [],
        citations: [],
        abstained: false,
        reason: '',
        incomplete: false,
        execution: meta,
      },
    })
    expect(msgs.find((m) => m.id === AID)?.execution?.task_id).toBe('exec-ab12')
  })

  it('普通问答 execution 为 null（可选字段缺席）', () => {
    const msgs = applySseEvent(seed(), AID, {
      event: 'answer',
      data: { facts: [], inferences: [], citations: [], abstained: false, reason: '', incomplete: false },
    })
    expect(msgs.find((m) => m.id === AID)?.execution).toBeNull()
  })
})

describe('ExecutionCard 三态渲染', () => {
  function cardOf(meta: ExecutionMetadata): string {
    const message: ChatMessage = {
      id: AID,
      role: 'assistant',
      text: '计划已生成',
      timestamp: '',
      execution: meta,
    }
    return renderToStaticMarkup(<ExecutionCard message={message} />)
  }

  it('planned：展示计划与批准/拒绝按钮', () => {
    const html = cardOf(metaOf('planned'))
    expect(html).toContain('待批准')
    expect(html).toContain('批准执行')
    expect(html).toContain('拒绝')
    expect(html).toContain('加限流')
    expect(html).toContain('app.py')
    expect(html).toContain('误伤')
  })

  it('executing：展示进度与中止', () => {
    const html = cardOf(metaOf('executing'))
    expect(html).toContain('执行中')
    expect(html).toContain('中止')
    expect(html).toContain('Edit')
  })

  it('review：展示 diff 摘要与合入/放弃', () => {
    const html = cardOf(metaOf('review'))
    expect(html).toContain('待验收')
    expect(html).toContain('验收并合入')
    expect(html).toContain('放弃')
    expect(html).toContain('+3')
    expect(html).toContain('−1')
  })

  it('merged：学习卡带 file:line 与概念 chips', () => {
    const html = cardOf(metaOf('merged'))
    expect(html).toContain('已合入')
    expect(html).toContain('这次改动学到了什么')
    expect(html).toContain('app.py:1')
    expect(html).toContain('#decorator')
    // 空影响面不渲染"影响 N 个"行（组件的空态行为）
    expect(html).not.toContain('个下游符号')
  })

  it('终态 failed：错误可见', () => {
    const html = cardOf(metaOf('failed', { error: 'claude 未能完成：error_max_turns' }))
    expect(html).toContain('执行失败')
    expect(html).toContain('error_max_turns')
  })
})
