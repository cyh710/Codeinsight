import { afterEach, describe, expect, it } from 'vitest'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { workbenchStore } from '../src/store/workbenchStore'
import { layoutStore } from '../src/store/layoutStore'
import LearningMarkdown from '../src/components/learning/LearningMarkdown'
import { textOffsets } from '../src/components/learning/selection'
import type { LearningTarget, ReadingContext } from '../src/api/types'

const topic = (version = 'v1', section_id = 'example'): LearningTarget => ({ topic_id: 'python-functions', title: '函数', version, section_id, href: `/learn/python-functions#${section_id}` })
const context: ReadingContext = { kind: 'knowledge', topic_id: 'python-functions', version: 'v1', section_id: 'example' }
afterEach(() => { workbenchStore.getState().resetProject(); layoutStore.getState().reset() })

describe('工作区行为', () => {
  it('同版本章节复用页签，版本不同分别保留，关闭后可恢复', () => {
    const s = workbenchStore.getState()
    s.openKnowledge(topic()); s.openKnowledge(topic('v1', 'definition'))
    expect(workbenchStore.getState().tabs).toHaveLength(2)
    s.openKnowledge(topic('v2'))
    expect(workbenchStore.getState().tabs).toHaveLength(3)
    const id = workbenchStore.getState().activeTab
    s.closeTab(id)
    expect(workbenchStore.getState().tabs).toHaveLength(2)
    s.reopenTab()
    expect(workbenchStore.getState().activeTab).toBe(id)
    expect(workbenchStore.getState().rightPanel).toMatchObject({ mode: 'knowledge', target: { version: 'v2' } })
  })
  it('固定材料与固定提问关联独立，取消后滚动和材料切换不会重新关联', () => {
    const s = workbenchStore.getState()
    s.openKnowledge(topic()); s.setReading(context); s.fixReading()
    s.openKnowledge(topic('v2')); s.setReading({ ...context, version: 'v2' })
    expect(workbenchStore.getState().reading?.kind).toBe('knowledge')
    expect(workbenchStore.getState().reading).toMatchObject({ version: 'v1' })
    s.setReading(null); s.setReading(context)
    expect(workbenchStore.getState().reading).toBeNull()
    s.followReading(); s.setReading(context)
    expect(workbenchStore.getState().reading).toEqual(context)
  })
  it('新证据不抢固定或隐藏的阅读区域，主动查看仍可打开', () => {
    const s = workbenchStore.getState()
    s.openKnowledge(topic()); s.setPinned(true); s.notifyEvidence()
    expect(workbenchStore.getState().rightPanel.mode).toBe('knowledge')
    expect(workbenchStore.getState().newEvidence).toBe(true)
    layoutStore.setState({ right: false }); s.setFollowEvidence(true); s.notifyEvidence()
    expect(layoutStore.getState().right).toBe(false)
    expect(workbenchStore.getState().rightPanel.mode).toBe('knowledge')
    s.openEvidence()
    expect(layoutStore.getState().right).toBe(true)
    expect(workbenchStore.getState().newEvidence).toBe(false)
  })
  it('恢复布局不清除材料、阅读关联或位置', () => {
    const s = workbenchStore.getState()
    s.openKnowledge(topic()); s.fixReading(context); s.setChatScroll(470)
    layoutStore.getState().resize('right', 600); layoutStore.getState().reset()
    expect(workbenchStore.getState().rightPanel.mode).toBe('knowledge')
    expect(workbenchStore.getState().reading).toEqual(context)
    expect(workbenchStore.getState().chatScroll).toBe(470)
  })
})

describe('Markdown 原文选区', () => {
  it('中文、emoji、转义和实体映射保持 UTF-16 原文边界', () => {
    expect(textOffsets('函数😀', '函数😀', 5)).toEqual([5, 6, 7, 8, 9])
    expect(textOffsets('a\\*b', 'a*b', 0)).toEqual([0, 1, 3, 4])
    expect(textOffsets('&amp;字', '&字', 0)).toEqual([0, 5, 6])
  })
  it('强调、链接和表格文字有源位置，教学代码保持原样', () => {
    const text = '看 **函数😀** 和 [表](/learn/sql-database)。\n\n| 名称 |\n| --- |\n| 示例 |\n\n```python\nx ** 2\n```'
    const html = renderToStaticMarkup(createElement(LearningMarkdown, { text, selectable: true }))
    const maps = [...html.matchAll(/data-source-map="(\[[\d,]+\])"/g)].map(m => JSON.parse(m[1]) as number[])
    const originals = maps.map(m => text.slice(m[0], m.at(-1)))
    expect(originals).toContain('函数😀')
    expect(originals).toContain('表')
    expect(originals).toContain('示例')
    expect(html).toContain('x ** 2')
    expect(html).not.toContain('href="/learn/sql-database"')
  })
})
