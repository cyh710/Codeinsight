import { afterEach, expect, it } from 'vitest'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import LearningMarkdown from '../src/components/learning/LearningMarkdown'
import FilePanel from '../src/components/evidence/FilePanel'
import { openSource, sourcePanel } from '../src/components/exploration/actions'
import { workbenchStore } from '../src/store/workbenchStore'
import { projectStore } from '../src/store/projectStore'

afterEach(() => workbenchStore.getState().resetProject())
const target = { topic_id: 'sql-transactions', section_id: 'two-writes', title: '事务', version: 'v1', href: '/learn/sql-transactions#two-writes' }
const link = '[事务](/learn/sql-transactions#two-writes)'
function excerpt(text: string) {
  return renderToStaticMarkup(createElement(LearningMarkdown, { text, targets: [target], excerptTarget: target }))
}

it('关联阅读提取完整相关段落，保留列表、表格和代码块，不依赖探索要点', () => {
  const paragraph = excerpt(`无关开场。\n\n项目中的两次写入需要${link}。读到句末。\n\n后续整篇内容。`)
  expect(paragraph).toContain('读到句末')
  expect(paragraph).not.toContain('无关开场')
  expect(paragraph).not.toContain('后续整篇')
  expect(excerpt('- 第一步\n- 查看' + link + '\n  \n  ```py\n  value = 1\n  ```\n- 最后一步')).toContain('value = 1')
  const table = excerpt(`| 作用 | 原理 |\n|---|---|\n| 写入 | ${link} |\n| 提交 | 一起完成 |`)
  expect(table).toContain('<table')
  expect(table).toContain('一起完成')
})

it('同一链接的首个完整块优先，无匹配不展示伪关联，代码内文本不算链接', () => {
  expect(excerpt(`第一段${link}。\n\n第二段${link}。`)).not.toContain('第二段')
  expect(excerpt('```md\n' + link + '\n```\n\n无匹配')).not.toContain('无匹配')
  expect(excerpt('只有普通项目说明。')).not.toContain('普通项目')
  expect(excerpt(`参考[事务][tx]。\n\n[tx]: ${target.href}`)).toContain('参考')
})

it('来源优先保存身份，缺版本等待主动打开当前文件，不借用全局索引', () => {
  projectStore.setState({ currentProjectId: 1 })
  workbenchStore.getState().setIndexVersion('latest')
  openSource({ path: 'app.py', lineno: 89 })
  expect(workbenchStore.getState().rightPanel).toMatchObject({ versionMissing: true, lineno: 89 })
  const html = renderToStaticMarkup(createElement(FilePanel, { path: 'app.py', lineno: 89, versionMissing: true }))
  expect(html).toContain('原版本未记录')
  expect(html).toContain('查看当前文件')
  const target = { kind: 'code' as const, project_id: 1, path: 'app.py', lineno: 5, source_kind: 'workspace' as const, content_sha256: 'saved' }
  expect(sourcePanel({ path: 'wrong.py', lineno: 99, target })).toMatchObject({ path: 'app.py', lineno: 5, contentSha: 'saved' })
  const before = workbenchStore.getState().rightPanel
  openSource({ path: 'another-project.py', lineno: 1, target: { ...target, project_id: 2 } })
  expect(workbenchStore.getState().rightPanel).toBe(before)
})
