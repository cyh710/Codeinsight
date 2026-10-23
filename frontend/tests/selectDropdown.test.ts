import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { createElement } from 'react'
import { parseOptionChildren } from '../src/components/common/selectOptions'

function readSource(path: string): string {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

describe('parseOptionChildren (原生 option JSX 兼容层)', () => {
  it('解析 value、文本 label 与 disabled', () => {
    const items = parseOptionChildren([
      createElement('option', { value: 'a' }, '选项甲'),
      createElement('option', { value: 'b', disabled: true }, '选项乙'),
    ])
    expect(items).toEqual([
      { value: 'a', label: '选项甲', disabled: false },
      { value: 'b', label: '选项乙', disabled: true },
    ])
  })

  it('缺省 value 时回退为文本内容，拼接数组子节点', () => {
    const items = parseOptionChildren([
      createElement('option', {}, '默认', '（开发者配置）'),
      createElement('option', { value: '' }, ''),
    ])
    expect(items).toEqual([
      { value: '默认（开发者配置）', label: '默认（开发者配置）', disabled: false },
      { value: '', label: '', disabled: false },
    ])
  })

  it('忽略非元素子节点与嵌套包装', () => {
    const items = parseOptionChildren([
      '裸文本',
      null,
      createElement('option', { value: 'x' }, 'X'),
    ])
    expect(items).toEqual([{ value: 'x', label: 'X', disabled: false }])
  })
})

describe('自绘 listbox 契约（ADR 0017）', () => {
  it('面板是 portal 渲染的 listbox，限高 7 行滚动窗口', () => {
    const source = readSource('../src/components/common/Select.tsx')
    expect(source).toContain('createPortal')
    expect(source).toContain('role="listbox"')
    expect(source).toContain('MAX_VISIBLE_ROWS = 7')
    expect(source).toContain('overflow-y-auto')
    expect(source).toContain('scrollbar-clean')
    // 键盘导航与读屏语义
    expect(source).toContain('aria-activedescendant')
    expect(source).toContain("case 'Escape'")
    // 触发器宽度与文本长度无关
    expect(source).toContain('w-full')
    expect(source).toContain('truncate')
  })

  it('面板入场动效走 motion tokens 且感知开启方向', () => {
    const css = readSource('../src/index.css')
    expect(css).toContain('@keyframes select-panel-in-down')
    expect(css).toContain('@keyframes select-panel-in-up')
    expect(css).toContain('var(--motion-fast)')
  })

  // CodeInsight 适配：织忆的调用方（settings/character/creation）未随基建
  // 复制，这里改成扫本仓的全部调用方。目前唯一调用方是左栏的项目切换器。
  it('原生 <select> 已全局退场（调用方全部迁移）', () => {
    for (const path of ['../src/components/tree/LeftPanel.tsx', '../src/App.tsx']) {
      expect(readSource(path), path).not.toContain('<select')
    }
    const left = readSource('../src/components/tree/LeftPanel.tsx')
    expect(left).toContain("from '../common/Select'")
  })
})
